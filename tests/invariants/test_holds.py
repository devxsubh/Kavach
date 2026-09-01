import pytest

from kavach.models import Buyer
from kavach.signing import KeyPair
from kavach.world import Database


def db_with_buyer(balance: int = 10000) -> Database:
    db = Database(":memory:")
    db.add_buyer(Buyer(id="buyer_01", name="Buyer", wallet_balance_minor=balance, pubkey=KeyPair().public_b64))
    return db


def test_hold_reduces_available_balance_without_debiting():
    db = db_with_buyer()
    db.place_hold("buyer_01", "order_a", 4000)
    assert db.get_buyer("buyer_01").wallet_balance_minor == 10000
    assert db.available_balance("buyer_01") == 6000


def test_concurrent_holds_cannot_oversubscribe_the_wallet():
    db = db_with_buyer(10000)
    db.place_hold("buyer_01", "order_a", 6000)
    # The second authorization sees the first claim, so the wallet cannot be spent twice.
    with pytest.raises(ValueError):
        db.place_hold("buyer_01", "order_b", 6000)
    assert db.available_balance("buyer_01") == 4000


def test_settling_a_hold_debits_exactly_once():
    db = db_with_buyer()
    db.place_hold("buyer_01", "order_a", 4000)
    db.settle_hold("order_a")
    db.settle_hold("order_a")
    assert db.get_buyer("buyer_01").wallet_balance_minor == 6000
    assert len(db.ledger_entries("order_a")) == 1
    assert db.hold_state("order_a") == "SETTLED"


def test_releasing_a_hold_returns_the_funds():
    db = db_with_buyer()
    db.place_hold("buyer_01", "order_a", 4000)
    db.release_hold("order_a")
    assert db.available_balance("buyer_01") == 10000
    assert db.hold_state("order_a") == "RELEASED"


def test_duplicate_hold_for_one_order_is_rejected():
    db = db_with_buyer()
    db.place_hold("buyer_01", "order_a", 1000)
    with pytest.raises(Exception):
        db.place_hold("buyer_01", "order_a", 1000)
    assert db.held_total("buyer_01") == 1000
