"""Exclusive marketplace sim: one buyer shops every honest stall."""

from kavach.agents.marketplace import MarketplaceRun
from kavach.config import KavachConfig
from kavach.signing import KeyPair
from kavach.world import Database, seed_world
from tests.adversarial.helpers import run_scenario


def _rules_config(*, guardrails: bool = True) -> KavachConfig:
    return KavachConfig(
        guardrails=guardrails,
        use_llm=False,
        llm_backend="ollama",
        llm_model="n/a",
        llm_base_url="http://127.0.0.1:11434",
        llm_api_key=None,
        ollama_host="http://127.0.0.1:11434",
        budget_burst_pct=0.15,
        strict_config=False,
    )


def _market_run(*, guardrails: bool = True, settle: bool = True) -> tuple[Database, object]:
    db = Database(":memory:")
    buyer, sellers = seed_world(db, seed=7, products_per_seller=8)
    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    result = MarketplaceRun(
        db, keys, guardrails=guardrails, config=_rules_config(guardrails=guardrails)
    ).run(goal_text="Find a wireless audio product", budget=15000, talk_seed=11, settle=settle)
    return db, result


def test_market_visits_five_stalls_and_settles_cheapest_handshake():
    db, result = _market_run()
    assert result.stalls_visited == 5
    assert {stall.seller_id for stall in result.stalls} == {
        "market_01",
        "market_02",
        "market_03",
        "market_04",
        "market_05",
    }
    accepted = [stall for stall in result.stalls if stall.accepted]
    assert accepted, "at least one stall should close a handshake"
    cheapest = min(accepted, key=lambda stall: (stall.negotiated_minor, stall.seller_id))
    assert result.winner is not None
    assert result.winner.seller_id == cheapest.seller_id
    assert result.winner.negotiated_minor == cheapest.negotiated_minor
    assert result.got_best_deal is True
    assert result.settled is True
    assert result.spent_minor == cheapest.negotiated_minor
    assert "Winner:" in result.summary
    assert "Best closed deal: yes" in result.summary
    orders = db.conn.execute("SELECT seller_id, state FROM orders").fetchall()
    assert len(orders) == 1
    assert orders[0]["seller_id"] == cheapest.seller_id
    assert orders[0]["state"] == "SETTLED"
    db.close()


def test_market_handshake_does_not_move_money_until_winner():
    db, result = _market_run(settle=False)
    assert result.winner is not None
    assert result.settled is False
    assert result.order_id
    assert result.spent_minor == 0
    orders = db.conn.execute("SELECT state FROM orders").fetchall()
    assert len(orders) == 1
    assert orders[0]["state"] != "SETTLED"
    db.close()


def test_attack_floor_still_blocks_bait_and_switch():
    db, result = run_scenario(seller_id="seller_04", guardrails=True)
    assert result.refusal_rule == "GR-9"
    assert result.settled is False
    db.close()
