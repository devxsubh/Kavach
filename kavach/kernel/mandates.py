from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel

from ..exceptions import GuardrailViolation, SignatureError
from ..models import CartMandate, IntentMandate, PaymentMandate
from ..signing import KeyPair

T = TypeVar("T", bound=BaseModel)


class SignedMandate(BaseModel, Generic[T]):
    payload: T
    issuer: str
    parent_id: str | None = None
    signature: str


class MandateAuthority:
    def __init__(self, keys: dict[str, KeyPair], public_keys: dict[str, str] | None = None):
        self.keys = keys
        self.public_keys = public_keys or {k: v.public_b64 for k, v in keys.items()}

    def issue(self, payload: T, issuer: str, parent_id: str | None = None) -> SignedMandate[T]:
        envelope = {"payload": payload.model_dump(mode="json"), "issuer": issuer, "parent_id": parent_id}
        return SignedMandate(payload=payload, issuer=issuer, parent_id=parent_id, signature=self.keys[issuer].sign(envelope))

    def verify(self, mandate: SignedMandate[T], expected_issuer: str | None = None) -> None:
        if expected_issuer and mandate.issuer != expected_issuer:
            raise GuardrailViolation("GR-4", "unexpected mandate issuer")
        key = self.public_keys.get(mandate.issuer)
        if not key:
            raise GuardrailViolation("GR-4", "unknown mandate issuer")
        if isinstance(mandate.payload, (IntentMandate, CartMandate)) and mandate.payload.expires_at <= datetime.now(timezone.utc):
            raise GuardrailViolation("GR-5", "mandate expired")
        envelope = {"payload": mandate.payload.model_dump(mode="json"), "issuer": mandate.issuer, "parent_id": mandate.parent_id}
        try:
            KeyPair.verify(key, envelope, mandate.signature)
        except SignatureError as exc:
            raise GuardrailViolation("GR-4", "invalid mandate signature") from exc

    def verify_chain(self, intent: SignedMandate[IntentMandate], cart: SignedMandate[CartMandate], payment: SignedMandate[PaymentMandate] | None = None) -> None:
        self.verify(intent)
        self.verify(cart)
        if cart.parent_id != intent.payload.intent_id or cart.payload.parent_intent_id != intent.payload.intent_id:
            raise GuardrailViolation("GR-4", "cart is not chained to intent")
        if payment:
            self.verify(payment)
            if payment.parent_id != cart.payload.cart_id or payment.payload.parent_cart_id != cart.payload.cart_id:
                raise GuardrailViolation("GR-4", "payment is not chained to cart")
