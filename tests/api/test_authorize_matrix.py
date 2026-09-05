"""HTTP authorize + floor roster for every seeded seller."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.service import CheckoutGateway, build_gateway_state
from kavach.config import KavachConfig
from kavach.payments import FakeRazorpayRail

from tests.adversarial.helpers import ATTACK_BY_SELLER, AUDIO_GOAL, AUDIO_MATRIX, SELLERS


def _config(**overrides) -> KavachConfig:
    defaults = dict(
        guardrails=True,
        use_llm=False,
        llm_backend="ollama",
        llm_model="n/a",
        llm_base_url="http://127.0.0.1:11434",
        llm_api_key=None,
        ollama_host="http://127.0.0.1:11434",
        budget_burst_pct=0.15,
        strict_config=False,
        payment_rail="razorpay",
        razorpay_key_id="rzp_test_fake",
        razorpay_key_secret="secret",
        razorpay_webhook_secret="secret",
    )
    defaults.update(overrides)
    return KavachConfig(**defaults)


def _client() -> tuple[TestClient, FakeRazorpayRail]:
    fake = FakeRazorpayRail()
    state = build_gateway_state(_config(), rail=fake)
    app = create_app(_config(), gateway=CheckoutGateway(state))
    return TestClient(app), fake


@pytest.mark.parametrize("seller_id", SELLERS)
@pytest.mark.parametrize("guardrails", [True, False], ids=["on", "off"])
def test_authorize_matches_scenario_matrix(seller_id: str, guardrails: bool):
    expected = AUDIO_MATRIX[(seller_id, guardrails)]
    client, fake = _client()
    before = len(fake.created)
    body = client.post(
        "/v1/checkout/authorize",
        json={
            "seller_id": seller_id,
            "guardrails": guardrails,
            "budget": 15000,
            "goal": AUDIO_GOAL,
        },
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["refusal_rule"] == expected.refusal_rule
    # Razorpay defers capture, so `allowed` means the kernel issued an order —
    # the same cases that settle on the simulated ledger (`last_phase == done`).
    if expected.last_phase == "done":
        assert payload["allowed"] is True
        assert payload["razorpay_order_id"] is not None
        assert len(fake.created) == before + 1
    else:
        assert payload["allowed"] is False
        assert payload["razorpay_order_id"] is None
        assert len(fake.created) == before


@pytest.mark.parametrize("seller_id", SELLERS)
def test_floor_roster_tracks_hired_seller(seller_id: str):
    client, _ = _client()
    response = client.get("/v1/floor", params={"seller_id": seller_id, "guardrails": "on"})
    assert response.status_code == 200
    body = response.json()
    assert body["hired_seller_id"] == seller_id
    seller = next(agent for agent in body["agents"] if agent["id"] == "seller")
    assert seller["hire_id"] == seller_id
    attack = ATTACK_BY_SELLER[seller_id]
    if attack is None:
        assert seller["sections"]["goal"]["current"] == "Honest counterparty"
    else:
        from kavach.adversarial.attacks import ATTACKS

        name = next(a.name for a in ATTACKS if a.attack_id == attack)
        assert seller["sections"]["goal"]["current"] == name
    kernel = next(agent for agent in body["agents"] if agent["id"] == "kernel")
    assert kernel["can_move_money"] is True


def test_each_seller_has_a_unique_floor_look():
    from kavach.agents.roster import SELLER_LOOKS

    client, _ = _client()
    looks = []
    for seller_id in SELLERS:
        body = client.get("/v1/floor", params={"seller_id": seller_id, "guardrails": "on"}).json()
        seller = next(agent for agent in body["agents"] if agent["id"] == "seller")
        archetype, accent, badge = SELLER_LOOKS[seller_id]
        assert seller["archetype"] == archetype
        assert seller["accent"] == accent
        assert seller["badge"] == badge
        looks.append(archetype)
    assert len(set(looks)) == len(SELLERS)
    merchants = client.get("/v1/merchants").json()["merchants"]
    assert {row["archetype"] for row in merchants} == {"sailor", "nordic", "neon", "ridge", "ember"}


def test_sellers_endpoint_lists_all_nine():
    client, _ = _client()
    response = client.get("/v1/sellers")
    assert response.status_code == 200
    rows = response.json()["sellers"]
    ids = [row["id"] for row in rows]
    assert ids == list(SELLERS)
    assert rows[3]["attack_class"] == "A-3"
    assert "GR-9" in rows[3]["blocked_by"]
