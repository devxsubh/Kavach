from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..agents import KavachRun
from ..agents.roster import DEFAULT_BUDGET, DEFAULT_GOAL, build_floor, seller_card
from ..config import KavachConfig
from ..exceptions import GuardrailViolation
from ..kernel import GuardrailKernel, MandateAuthority
from ..kernel.policy import RULES
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
    last_run: dict[str, Any] | None = None


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


def _money(minor: int) -> str:
    return f"${minor / 100:,.2f}"


def _messages_from_story(story: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    buyer_re = re.compile(r'Buyer: "([\s\S]*?)"')
    seller_re = re.compile(r'Seller: "([\s\S]*?)"')
    for step in story:
        detail = step.get("detail") or ""
        phase = step.get("phase") or ""
        title = step.get("title") or ""
        buyer = buyer_re.search(detail)
        seller = seller_re.search(detail)
        if buyer:
            msgs.append({"who": "buyer", "kind": "OFFER", "text": buyer.group(1), "phase": phase})
        if seller:
            msgs.append({"who": "seller", "kind": "COUNTER", "text": seller.group(1), "phase": phase})
        if not buyer and not seller and phase in {"checkout", "refuse", "done"}:
            text = f"{title} — {detail}" if detail else title
            msgs.append({"who": "kernel", "kind": "NOTE", "text": text, "phase": phase})
    return msgs


class CheckoutGateway:
    def __init__(self, state: GatewayState):
        self.state = state

    def list_sellers(self) -> list[dict[str, Any]]:
        return [seller_card(s) for s in self.state.sellers]

    def _remember_run(
        self,
        *,
        scenario: ScenarioResult,
        story: list[dict[str, str]],
        allowed: bool,
        amount_minor: int = 0,
    ) -> None:
        self.state.last_run = {
            "product_title": scenario.product_title,
            "product_id": scenario.product_id,
            "attack_class": scenario.attack_class,
            "allowed": allowed,
            "refusal_rule": scenario.refusal_rule,
            "amount_minor": amount_minor or scenario.spent_minor,
            "order_id": scenario.order_id,
            "settled": scenario.settled,
            "story": story,
            "guardrails": scenario.guardrails,
        }

    def world_snapshot(
        self,
        *,
        seller_id: str = "seller_04",
        goal: str = DEFAULT_GOAL,
        budget: int = DEFAULT_BUDGET,
        guardrails: bool | None = None,
    ) -> dict[str, Any]:
        """Live contents of every floor station / room for the demo inspect UI."""
        rails = self.state.config.guardrails if guardrails is None else guardrails
        buyer = self.state.db.get_buyer(self.state.buyer_id)
        hired = next((s for s in self.state.sellers if s.id == seller_id), self.state.sellers[0])
        products = [p for p in self.state.db.search_products() if p.seller_id == hired.id]
        catalog: list[dict[str, Any]] = []
        for product in products[:12]:
            reviews = self.state.db.list_reviews(product.id)
            catalog.append(
                {
                    "id": product.id,
                    "title": product.title,
                    "price": _money(product.list_price_minor),
                    "price_minor": product.list_price_minor,
                    "stock": product.stock,
                    "category": product.attributes.get("category"),
                    "wireless": product.attributes.get("wireless"),
                    "color": product.attributes.get("color"),
                    "description": product.description[:220],
                    "reviews": len(reviews),
                    "synthetic_reviews": sum(1 for r in reviews if r.is_synthetic),
                }
            )

        last = self.state.last_run or {}
        story = last.get("story") or []
        mail = _messages_from_story(story)
        held = self.state.db.held_total(buyer.id)
        available = self.state.db.available_balance(buyer.id)
        audit = self.state.db.audit_events()[-24:]
        orders: list[dict[str, Any]] = []
        if last.get("order_id"):
            try:
                order = self.state.db.get_order(last["order_id"])
                state_val = order.state.value if hasattr(order.state, "value") else str(order.state)
                orders.append(
                    {
                        "id": order.id,
                        "state": state_val,
                        "product_id": order.product_id,
                        "amount": _money(order.unit_price_minor * order.qty),
                        "seller_id": order.seller_id,
                    }
                )
            except KeyError:
                pass

        return {
            "goal": goal,
            "budget": _money(budget),
            "budget_minor": budget,
            "guardrails": rails,
            "hired_seller_id": hired.id,
            "hired_seller_name": hired.name,
            "last_run": {
                "product_title": last.get("product_title"),
                "attack_class": last.get("attack_class"),
                "allowed": last.get("allowed"),
                "refusal_rule": last.get("refusal_rule"),
                "amount_minor": last.get("amount_minor"),
                "order_id": last.get("order_id"),
                "settled": last.get("settled"),
            }
            if last
            else None,
            "stations": {
                "catalog": {
                    "id": "catalog",
                    "name": "Catalog shelf",
                    "blurb": f"Products from {hired.name}. Discovery binds the cart (GR-8).",
                    "items": catalog,
                },
                "mailbox": {
                    "id": "mailbox",
                    "name": "Mailbox",
                    "blurb": "Signed OFFER / COUNTER envelopes from the last run.",
                    "messages": mail,
                    "empty_hint": "Authorize checkout to fill the mailbox with negotiation mail.",
                },
                "vault": {
                    "id": "vault",
                    "name": "Vault",
                    "blurb": "Wallet holds and settles only through the kernel.",
                    "wallet": _money(buyer.wallet_balance_minor),
                    "wallet_minor": buyer.wallet_balance_minor,
                    "held": _money(held),
                    "held_minor": held,
                    "available": _money(available),
                    "available_minor": available,
                    "orders": orders,
                    "payment_rail": self.state.config.payment_label,
                },
                "board": {
                    "id": "board",
                    "name": "Audit board",
                    "blurb": "Append-only hash chain. Replay must reconstruct every settle.",
                    "events": [
                        {
                            "seq": e.seq,
                            "actor": e.actor,
                            "event_type": e.event_type,
                            "hash": e.hash[:10],
                            "payload": {k: e.payload[k] for k in list(e.payload)[:4]},
                        }
                        for e in audit
                    ],
                    "empty_hint": "No audit events yet — run a checkout to stamp the board.",
                },
                "kernel": {
                    "id": "kernel",
                    "name": "Kernel office",
                    "blurb": "GOD of this floor. The only desk that can move money.",
                    "guardrails": "ON" if rails else "OFF",
                    "rules": [{"id": code, "label": label} for code, label in RULES.items()],
                },
                "advisor": {
                    "id": "advisor",
                    "name": "Advisor booth",
                    "blurb": "Suggests JSON. Never writes the world.",
                    "llm": self.state.config.llm_label,
                    "mode": "ON" if self.state.config.use_llm else "OFF (rules talk)",
                    "backend": self.state.config.llm_backend if self.state.config.use_llm else "rules",
                },
                "hall": {
                    "id": "hall",
                    "name": "Negotiation floor",
                    "blurb": "Buyer and seller haggle at the table. Cooler is just a cooler.",
                    "spots": [
                        {"id": "table", "name": "Deal table", "detail": "Where offers and counters land."},
                        {"id": "cooler", "name": "Water cooler", "detail": "Break-room gossip. No mandates here."},
                        {
                            "id": "desks",
                            "name": "Buyer & seller desks",
                            "detail": f"Buyer brief: {goal} · budget {_money(budget)}. Hired: {hired.id}.",
                        },
                    ],
                },
            },
        }

    def list_floor(
        self,
        *,
        seller_id: str = "seller_04",
        goal: str = DEFAULT_GOAL,
        budget: int = DEFAULT_BUDGET,
        guardrails: bool | None = None,
    ) -> dict[str, Any]:
        buyer = self.state.db.get_buyer(self.state.buyer_id)
        floor = build_floor(
            config=self.state.config,
            buyer=buyer,
            sellers=self.state.sellers,
            seller_id=seller_id,
            goal=goal,
            budget=budget,
            guardrails=guardrails,
        )
        floor["world"] = self.world_snapshot(
            seller_id=seller_id,
            goal=goal,
            budget=budget,
            guardrails=guardrails,
        )
        return floor

    def run_scenario(
        self,
        *,
        goal: str,
        budget: int,
        seller_id: str,
        guardrails: bool | None = None,
    ) -> ScenarioResult:
        rails = self.state.config.guardrails if guardrails is None else guardrails
        result = KavachRun(
            self.state.db,
            self.state.keys,
            guardrails=rails,
            config=self.state.config,
            payment_rail="simulated",
        ).run(goal_text=goal, budget=budget, seller_id=seller_id, scenario_id="api_run")
        story = [{"phase": s.phase, "title": s.title, "detail": s.detail} for s in result.story]
        self._remember_run(scenario=result, story=story, allowed=result.settled, amount_minor=result.spent_minor)
        return result

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
            self._remember_run(scenario=scenario, story=story, allowed=False)
            return AuthorizeOutcome(
                allowed=False,
                scenario=scenario,
                message=scenario.refusal_rule or "checkout not authorized",
                story=story,
            )

        if not use_rzp:
            self._remember_run(
                scenario=scenario,
                story=story,
                allowed=True,
                amount_minor=scenario.spent_minor,
            )
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
        self._remember_run(scenario=scenario, story=story, allowed=True, amount_minor=amount)
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
