from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..agents import KavachRun
from ..config import KavachConfig
from ..exceptions import GuardrailViolation
from ..kernel import GuardrailKernel, MandateAuthority
from ..models import ScenarioResult
from ..payments import RazorpayRail
from ..payments.base import PaymentRail
from ..signing import KeyPair
from ..world import Database, seed_world


@dataclass
class GatewayState:
    """Process-local world used by the HTTP gateway (one in-memory Kavach world)."""

    config: KavachConfig
    db: Database
    keys: dict[str, KeyPair]
    rail: PaymentRail | None
    buyer_id: str = "buyer_01"
    sellers: list = field(default_factory=list)


def build_gateway_state(config: KavachConfig | None = None, *, rail: PaymentRail | None = None) -> GatewayState:
    config = config or KavachConfig.from_env()
    db = Database(":memory:")
    buyer, sellers = seed_world(db, products_per_seller=8)
    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    payment: PaymentRail | None = rail
    if payment is None and config.payment_rail == "razorpay":
        if config.razorpay_key_id and config.razorpay_key_secret:
            payment = RazorpayRail(config)
    return GatewayState(config=config, db=db, keys=keys, rail=payment, buyer_id=buyer.id, sellers=sellers)


@dataclass
class AuthorizeOutcome:
    allowed: bool
    scenario: ScenarioResult
    kavach_order_id: str | None = None
    amount_minor: int = 0
    currency: str = "INR"
    razorpay_order_id: str | None = None
    razorpay_key_id: str | None = None
    message: str = ""
    story: list[dict[str, str]] = field(default_factory=list)


class CheckoutGateway:
    def __init__(self, state: GatewayState):
        self.state = state

    def list_sellers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "attack_class": s.attack_class,
                "is_adversarial": s.is_adversarial,
            }
            for s in self.state.sellers
        ]

    def run_scenario(
        self,
        *,
        goal: str,
        budget: int,
        seller_id: str,
        guardrails: bool | None = None,
    ) -> ScenarioResult:
        rails = self.state.config.guardrails if guardrails is None else guardrails
        return KavachRun(
            self.state.db,
            self.state.keys,
            guardrails=rails,
            config=self.state.config,
            payment_rail="simulated",
        ).run(goal_text=goal, budget=budget, seller_id=seller_id, scenario_id="api_run")

    def authorize(
        self,
        *,
        goal: str,
        budget: int,
        seller_id: str,
        guardrails: bool | None = None,
    ) -> AuthorizeOutcome:
        """Negotiate → kernel authorize. Create Razorpay order only if the kernel allows."""
        rails = self.state.config.guardrails if guardrails is None else guardrails
        use_rzp = self.state.config.payment_rail == "razorpay" and self.state.rail is not None
        runner = KavachRun(
            self.state.db,
            self.state.keys,
            guardrails=rails,
            config=self.state.config,
            payment_rail="razorpay" if use_rzp else "simulated",
        )
        scenario = runner.run(
            goal_text=goal,
            budget=budget,
            seller_id=seller_id,
            scenario_id="api_checkout",
            settle=not use_rzp,
        )
        story = [{"phase": s.phase, "title": s.title, "detail": s.detail} for s in scenario.story]

        if scenario.refusal_rule or not scenario.order_id:
            return AuthorizeOutcome(
                allowed=False,
                scenario=scenario,
                message=scenario.refusal_rule or "checkout not authorized",
                story=story,
            )

        if not use_rzp:
            return AuthorizeOutcome(
                allowed=True,
                scenario=scenario,
                kavach_order_id=scenario.order_id,
                amount_minor=scenario.spent_minor,
                message="settled on simulated ledger",
                story=story,
            )

        # Kernel allowed — only now may we call Razorpay.
        order = self.state.db.get_order(scenario.order_id)
        amount = order.unit_price_minor * order.qty
        external = self.state.rail.create_order(
            amount_minor=amount,
            currency="INR",
            receipt=order.id.replace("_", "")[:40],
            notes={"kavach_order_id": order.id, "seller_id": order.seller_id},
        )
        self.state.db.save_payment_ref(
            order_id=order.id,
            provider=external.provider,
            external_id=external.external_id,
            amount_minor=external.amount_minor,
            currency=external.currency,
            status="CREATED",
        )
        self.state.db.append_audit(
            "razorpay",
            "RAZORPAY_ORDER_CREATED",
            {"order_id": order.id, "external_id": external.external_id, "amount_minor": amount},
        )
        key_id = getattr(self.state.rail, "key_id", None)
        return AuthorizeOutcome(
            allowed=True,
            scenario=scenario,
            kavach_order_id=order.id,
            amount_minor=amount,
            currency=external.currency,
            razorpay_order_id=external.external_id,
            razorpay_key_id=key_id,
            message="kernel allowed — complete payment in Razorpay Checkout",
            story=story,
        )

    def confirm_client_payment(self, order_id: str, payment_id: str, signature: str) -> dict[str, Any]:
        if self.state.rail is None:
            raise GuardrailViolation("RAIL", "payment rail is not configured")
        if not self.state.rail.verify_payment_signature(order_id, payment_id, signature):
            raise GuardrailViolation("RAIL", "invalid Razorpay payment signature")
        return self._capture(order_id, payment_id)

    def handle_webhook(self, body: bytes, signature: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.state.rail is None:
            raise GuardrailViolation("RAIL", "payment rail is not configured")
        if not self.state.rail.verify_webhook_signature(body, signature):
            raise GuardrailViolation("RAIL", "invalid Razorpay webhook signature")
        event = payload.get("event")
        if event != "payment.captured":
            return {"ok": True, "ignored": event}
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_order = entity.get("order_id")
        payment_id = entity.get("id")
        if not rzp_order:
            raise GuardrailViolation("RAIL", "webhook missing order_id")
        return self._capture(rzp_order, payment_id)

    def _capture(self, razorpay_order_id: str, payment_id: str | None) -> dict[str, Any]:
        ref = self.state.db.get_payment_ref_by_external(razorpay_order_id)
        if not ref:
            raise GuardrailViolation("RAIL", f"unknown Razorpay order {razorpay_order_id}")
        order = self.state.db.get_order(ref["order_id"])
        self.state.db.update_payment_ref(razorpay_order_id, status="CAPTURED", payment_id=payment_id)
        self.state.db.append_audit(
            "razorpay",
            "RAZORPAY_PAYMENT_CAPTURED",
            {"order_id": order.id, "external_id": razorpay_order_id, "payment_id": payment_id},
        )
        kernel = GuardrailKernel(
            self.state.db,
            MandateAuthority(self.state.keys),
            guardrails=True,
            payment_rail="razorpay",
        )
        settled = kernel.capture_external_payment(order, payment_id=payment_id, provider="razorpay")
        return {"ok": True, "kavach_order_id": settled.id, "state": settled.state.value}
