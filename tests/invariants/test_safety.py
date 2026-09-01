import pytest

from kavach.exceptions import GuardrailViolation
from kavach.kernel import GuardrailKernel, MandateAuthority
from kavach.models import CartLine, CartMandate, Constraint, IntentMandate
from kavach.signing import KeyPair
from kavach.world import Database
from kavach.models import Buyer, Product, Seller


def test_wallet_never_goes_negative():
    db = Database(":memory:")
    db.add_buyer(Buyer(id="b", name="B", wallet_balance_minor=10, pubkey=KeyPair().public_b64))
    with pytest.raises(ValueError):
        db.debit("b", -11, "test")
    assert db.get_buyer("b").wallet_balance_minor == 10


def test_price_binding_refuses_bait_and_switch():
    db = Database(":memory:")
    buyer_key, kernel_key = KeyPair(), KeyPair()
    db.add_buyer(Buyer(id="b", name="B", wallet_balance_minor=10000, pubkey=buyer_key.public_b64))
    db.add_seller(Seller(id="s", name="S", policy_profile="exploitative", price_floor_pct=.5, pubkey=KeyPair().public_b64))
    db.add_product(Product(id="p", seller_id="s", title="P", description="", list_price_minor=1000, stock=1, attributes={"category":"audio"}))
    auth = MandateAuthority({"b": buyer_key, "kernel": kernel_key})
    kernel = GuardrailKernel(db, auth)
    intent = IntentMandate(buyer_id="b", goal_text="audio", budget_ceiling_minor=5000)
    cart = CartMandate(parent_intent_id=intent.intent_id, lines=[CartLine(product_id="p", seller_id="s", unit_price_minor=2000, qty=1)], total_minor=2000, negotiation_transcript_hash="signed-transcript")
    si, sc = auth.issue(intent, "b"), auth.issue(cart, "b", intent.intent_id)
    kernel.register_candidates("session", [db.get_product("p")])
    with pytest.raises(GuardrailViolation, match="GR-9"):
        kernel.verify_cart("session", si, sc, committed_prices={"p": 1000})


def test_payment_authorization_is_idempotent():
    db = Database(":memory:")
    buyer_key, kernel_key = KeyPair(), KeyPair()
    db.add_buyer(Buyer(id="b", name="B", wallet_balance_minor=10000, pubkey=buyer_key.public_b64))
    db.add_seller(Seller(id="s", name="S", policy_profile="linear", price_floor_pct=.5, pubkey=KeyPair().public_b64))
    db.add_product(Product(id="p", seller_id="s", title="P", description="", list_price_minor=1000, stock=1, attributes={"category":"audio"}))
    auth = MandateAuthority({"b": buyer_key, "kernel": kernel_key})
    kernel = GuardrailKernel(db, auth)
    intent = IntentMandate(buyer_id="b", goal_text="audio", budget_ceiling_minor=5000)
    cart = CartMandate(parent_intent_id=intent.intent_id, lines=[CartLine(product_id="p", seller_id="s", unit_price_minor=1000, qty=1)], total_minor=1000, negotiation_transcript_hash="signed-transcript")
    si, sc = auth.issue(intent, "b"), auth.issue(cart, "b", intent.intent_id)
    kernel.register_candidates("session", [db.get_product("p")])
    order = kernel.reserve_stock("session", sc, buyer_id="b")
    payment = kernel.issue_payment(si, sc, "b")
    first = kernel.authorize_payment("session", si, sc, payment, order)
    second = kernel.authorize_payment("session", si, sc, payment, first)
    assert first.state == second.state
    assert db.get_buyer("b").wallet_balance_minor == 9000
