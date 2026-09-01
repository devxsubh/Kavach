from kavach.agents import KavachRun
from kavach.config import KavachConfig
from kavach.signing import KeyPair
from kavach.world import Database, seed_world


def _runner(guardrails: bool) -> tuple[Database, KavachRun]:
    db = Database(":memory:")
    buyer, sellers = seed_world(db, products_per_seller=8)
    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    config = KavachConfig(
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
    return db, KavachRun(db, keys, guardrails=guardrails, config=config)


def test_a3_guardrails_on_refuses_price_switch():
    db, runner = _runner(guardrails=True)
    result = runner.run(seller_id="seller_04", budget=15000)
    titles = [s.title for s in result.story]
    assert any("switches the price" in t for t in titles)
    assert result.settled is False
    assert result.refusal_rule == "GR-9"
    assert result.attack_succeeded is False
    assert result.spent_minor == 0
    db.close()


def test_a3_guardrails_off_lets_switch_succeed():
    db, runner = _runner(guardrails=False)
    result = runner.run(seller_id="seller_04", budget=15000)
    titles = [s.title for s in result.story]
    assert any("switches the price" in t for t in titles)
    assert result.settled is True
    assert result.attack_succeeded is True
    assert result.spent_minor > 0
    assert result.refusal_rule is None
    db.close()
