from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExternalOrder:
    """Provider order created only after the kernel allows checkout."""

    provider: str
    external_id: str
    amount_minor: int
    currency: str
    raw: dict


class PaymentRail(Protocol):
    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> ExternalOrder: ...

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool: ...

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool: ...
