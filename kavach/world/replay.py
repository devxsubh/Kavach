from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..exceptions import ReplayError
from ..models import OrderState
from .db import Database


SETTLEMENT_MILESTONES = ("STOCK_RESERVED", "FUNDS_HELD", "PAYMENT_AUTHORIZED", "ORDER_SETTLED")


def _appears_in_order(event_types: Iterable[str], milestones: Sequence[str]) -> bool:
    remaining = iter(event_types)
    return all(any(seen == milestone for seen in remaining) for milestone in milestones)


def replay_order(db: Database, order_id: str) -> bool:
    """Reconstruct the order's lifecycle from the audit log and verify money moved as recorded."""
    db.verify_audit_chain()
    order = db.get_order(order_id)
    if order.state != OrderState.SETTLED:
        raise ReplayError(f"order {order_id} is not settled")
    event_types = [e.event_type for e in db.audit_events() if e.payload.get("order_id") == order_id]
    if not _appears_in_order(event_types, SETTLEMENT_MILESTONES):
        raise ReplayError(f"order {order_id} does not have a reproducible settlement trail")
    if event_types[-1] != "ORDER_SETTLED":
        raise ReplayError(f"order {order_id} recorded activity after settlement")
    if db.hold_state(order_id) != "SETTLED":
        raise ReplayError(f"order {order_id} settled without a settled funds hold")
    # A settled order must be backed by exactly one debit matching its total.
    debits = [entry for entry in db.ledger_entries(order_id) if entry["delta"] < 0]
    expected_total = order.unit_price_minor * order.qty
    if len(debits) != 1 or -debits[0]["delta"] != expected_total:
        raise ReplayError(f"order {order_id} is not backed by a matching ledger debit")
    return True
