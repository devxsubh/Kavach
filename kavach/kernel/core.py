from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NoReturn

from ..exceptions import GuardrailViolation, IllegalTransition
from ..models import CartMandate, IntentMandate, Order, OrderState, PaymentMandate, Product, new_id
from ..signing import KeyPair
from ..world.db import Database
from .escalation import EscalationGate
from .firewall import InputFirewall
from .mandates import MandateAuthority, SignedMandate


TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.DRAFT: {OrderState.RESERVED, OrderState.REFUSED, OrderState.CANCELLED},
    OrderState.RESERVED: {OrderState.AUTHORIZED, OrderState.CANCELLED, OrderState.REFUSED},
    OrderState.AUTHORIZED: {OrderState.SETTLED, OrderState.CANCELLED, OrderState.REFUSED},
    OrderState.SETTLED: set(), OrderState.CANCELLED: set(), OrderState.REFUSED: set(),
}


def transition(order: Order, target: OrderState) -> Order:
    if target not in TRANSITIONS[order.state]:
        raise IllegalTransition(f"{order.state.value} -> {target.value}")
    return order.model_copy(update={"state": target})


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq": return actual == expected
    if operator == "neq": return actual != expected
    if operator == "lte": return actual <= expected
    if operator == "gte": return actual >= expected
    if operator == "in": return actual in expected
    if operator == "contains": return expected in actual
    return False


def satisfies_constraint(product: Product, constraint: Any) -> bool:
    return _compare(product.attributes.get(constraint.attribute), constraint.operator.value, constraint.value)


class GuardrailKernel:
    def __init__(
        self,
        db: Database,
        authority: MandateAuthority,
        *,
        guardrails: bool = True,
        max_rounds: int = 6,
        max_tool_calls: int = 30,
        payment_rail: str = "simulated",
    ):
        self.db = db
        self.authority = authority
        self.guardrails = guardrails
        self.payment_rail = payment_rail
        self.firewall = InputFirewall(enabled=guardrails)
        self.escalation = EscalationGate(db)
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls
        self.tool_calls: dict[str, int] = {}
        self.candidates: dict[str, set[str]] = {}
        self.committed_prices: dict[str, int] = {}
        self.refusals: list[tuple[str, str]] = []

    def _record(self, rule: str, message: str, actor: str = "kernel") -> None:
        self.refusals.append((rule, message))
        self.db.append_audit(actor, "GUARDRAIL_REFUSAL", {"rule_id": rule, "message": message})

    def _refuse(self, rule: str, message: str, actor: str = "kernel") -> NoReturn:
        self._record(rule, message, actor)
        raise GuardrailViolation(rule, message)

    def _refuse_all(self, violations: list[tuple[str, str]], actor: str = "kernel") -> NoReturn:
        """Report every boundary that failed, not only the first one hit."""
        for rule, message in violations:
            self._record(rule, message, actor)
        first_rule, first_message = violations[0]
        raise GuardrailViolation(first_rule, first_message, violations)

    def _call(self, session_id: str) -> None:
        self.tool_calls[session_id] = self.tool_calls.get(session_id, 0) + 1
        if self.guardrails and self.tool_calls[session_id] > self.max_tool_calls:
            self._refuse("GR-11", "tool call limit exceeded")

    def register_candidates(self, session_id: str, products: list[Product]) -> list[Product]:
        self._call(session_id)
        self.candidates[session_id] = {p.id for p in products}
        self.db.append_audit("discovery", "CANDIDATE_SET", {"session_id": session_id, "product_ids": sorted(self.candidates[session_id])})
        return [p.model_copy(deep=True) for p in products]

    def sanitize_untrusted(self, actor: str, label: str, text: str) -> str:
        self._call(actor)
        result = self.firewall.scan(text)
        self.db.append_audit(actor, "FIREWALL_SCAN", {"label": label, "flagged": result.flagged, "reasons": list(result.reasons)})
        return result.sanitized

    def verify_cart(self, session_id: str, intent: SignedMandate[IntentMandate], cart: SignedMandate[CartMandate], *, committed_prices: dict[str, int] | None = None) -> None:
        if not self.guardrails:
            return
        # An unverifiable mandate chain short-circuits: nothing downstream can be trusted.
        try:
            self.authority.verify_chain(intent, cart)
        except GuardrailViolation as exc:
            self._refuse(exc.rule_id, exc.message)

        violations: list[tuple[str, str]] = []
        if cart.payload.total_minor != sum(line.unit_price_minor * line.qty for line in cart.payload.lines):
            violations.append(("GR-6", "cart total does not equal its lines"))
        if cart.payload.total_minor > intent.payload.budget_ceiling_minor:
            violations.append(("GR-6", "cart exceeds intent budget"))
        if sum(line.qty for line in cart.payload.lines) > intent.payload.max_items:
            violations.append(("GR-7", "cart exceeds max items"))
        allowed = set(intent.payload.allowed_categories)
        for line in cart.payload.lines:
            if line.product_id not in self.candidates.get(session_id, set()):
                violations.append(("GR-8", f"cart contains undiscovered product {line.product_id}"))
            product = self.db.get_product(line.product_id)
            if allowed and product.attributes.get("category") not in allowed:
                violations.append(("GR-7", "product category violates intent"))
            for constraint in intent.payload.hard_constraints:
                if not _compare(product.attributes.get(constraint.attribute), constraint.operator.value, constraint.value):
                    violations.append(("GR-7", f"constraint failed: {constraint.attribute}"))
            if committed_prices and committed_prices.get(line.product_id) != line.unit_price_minor:
                violations.append(("GR-9", "checkout price differs from signed negotiation commitment"))
        if violations:
            self._refuse_all(violations)

    def reserve_stock(self, session_id: str, cart: SignedMandate[CartMandate], line_index: int = 0, buyer_id: str = "buyer_01") -> Order:
        self._call(session_id)
        line = cart.payload.lines[line_index]
        product = self.db.get_product(line.product_id)
        if product.stock < line.qty:
            self._refuse("TOOL.reserve_stock", "insufficient stock")
        order = Order(id=new_id("order"), buyer_id=buyer_id, seller_id=line.seller_id, product_id=line.product_id, unit_price_minor=line.unit_price_minor, qty=line.qty, cart_mandate_id=cart.payload.cart_id, idempotency_key=f"{cart.payload.cart_id}:{line.product_id}:{line_index}")
        self.db.insert_order(order)
        self.db.update_stock(product.id, -line.qty)
        order = transition(order, OrderState.RESERVED)
        self.db.update_order(order)
        self.db.append_audit("kernel", "STOCK_RESERVED", {"order_id": order.id, "product_id": product.id, "qty": line.qty})
        return order

    @staticmethod
    def requires_approval(intent: SignedMandate[IntentMandate], amount_minor: int) -> bool:
        threshold = intent.payload.requires_human_approval_above_minor
        return threshold > 0 and amount_minor >= threshold

    def issue_payment(self, intent: SignedMandate[IntentMandate], cart: SignedMandate[CartMandate], buyer_id: str, *, approval_ref: str | None = None) -> SignedMandate[PaymentMandate]:
        payment = PaymentMandate(parent_cart_id=cart.payload.cart_id, amount_minor=cart.payload.total_minor, buyer_id=buyer_id, idempotency_key=f"pay:{cart.payload.cart_id}", human_approval_ref=approval_ref)
        return self.authority.issue(payment, "kernel", parent_id=cart.payload.cart_id)

    def authorize_payment(self, session_id: str, intent: SignedMandate[IntentMandate], cart: SignedMandate[CartMandate], payment: SignedMandate[PaymentMandate], order: Order) -> Order:
        self._call(session_id)
        self.verify_cart(session_id, intent, cart, committed_prices={line.product_id: line.unit_price_minor for line in cart.payload.lines})
        if payment.payload.amount_minor != cart.payload.total_minor:
            self._refuse("GR-6", "payment amount mismatch")
        if payment.payload.amount_minor > intent.payload.budget_ceiling_minor:
            self._refuse("GR-6", "payment exceeds budget")
        if self.guardrails:
            if payment.payload.buyer_id != intent.payload.buyer_id:
                self._refuse("GR-4", "payment buyer mismatch")
            if self.requires_approval(intent, payment.payload.amount_minor) and not payment.payload.human_approval_ref:
                self.escalation.request(payment.payload.buyer_id, order.seller_id, payment.payload.amount_minor, "payment above human approval threshold")
                self._refuse("GR-12", "human approval required")
            try:
                self.authority.verify_chain(intent, cart, payment)
            except GuardrailViolation as exc:
                self._refuse(exc.rule_id, exc.message)
        if self.db.has_ledger_entry(order.id):
            self.db.append_audit("kernel", "PAYMENT_REPLAY_NOOP", {"idempotency_key": payment.payload.idempotency_key, "order_id": order.id})
            return order
        if order.state != OrderState.RESERVED:
            self._refuse("TOOL.authorize_payment", "order is not reserved")
        # Hold first: the funds check and the claim on them happen in one transaction,
        # so a concurrent authorization cannot spend the same balance twice.
        try:
            self.db.place_hold(payment.payload.buyer_id, order.id, payment.payload.amount_minor)
        except ValueError:
            self._refuse("GR-10", "wallet debit would go negative")
        self.db.append_audit("kernel", "FUNDS_HELD", {"order_id": order.id, "amount_minor": payment.payload.amount_minor})
        # Simulated rail captures immediately. Razorpay keeps the hold until external capture.
        if self.payment_rail != "razorpay":
            try:
                self.db.settle_hold(order.id, "order authorization")
            except Exception:
                self.db.release_hold(order.id)
                self.db.append_audit("kernel", "FUNDS_RELEASED", {"order_id": order.id})
                raise
        order = transition(order, OrderState.AUTHORIZED).model_copy(update={"payment_mandate_id": payment.payload.payment_id})
        self.db.update_order(order)
        self.db.append_audit("kernel", "PAYMENT_AUTHORIZED", {"order_id": order.id, "amount_minor": payment.payload.amount_minor})
        return order

    def capture_external_payment(self, order: Order, *, payment_id: str | None = None, provider: str = "razorpay") -> Order:
        """Settle a held wallet and mark the order SETTLED after an external rail confirms payment."""
        if order.state == OrderState.SETTLED:
            return order
        if order.state != OrderState.AUTHORIZED:
            self._refuse("TOOL.capture_external_payment", "order is not authorized")
        if self.db.hold_state(order.id) == "HELD":
            self.db.settle_hold(order.id, f"{provider} capture")
            self.db.append_audit("kernel", "FUNDS_CAPTURED", {"order_id": order.id, "provider": provider, "payment_id": payment_id})
        return self.settle_order(order)

    def settle_order(self, order: Order) -> Order:
        order = transition(order, OrderState.SETTLED)
        self.db.update_order(order)
        self.db.append_audit("fulfillment", "ORDER_SETTLED", {"order_id": order.id})
        return order
