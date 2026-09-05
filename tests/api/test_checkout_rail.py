import json

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.service import CheckoutGateway, build_gateway_state
from kavach.config import KavachConfig
from kavach.payments import FakeRazorpayRail


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


def _gateway(guardrails_default: bool = True) -> tuple[CheckoutGateway, FakeRazorpayRail]:
    fake = FakeRazorpayRail()
    cfg = _config(guardrails=guardrails_default)
    state = build_gateway_state(cfg, rail=fake)
    return CheckoutGateway(state), fake


def test_refuse_path_never_creates_razorpay_order():
    gateway, fake = _gateway()
    outcome = gateway.authorize(
        goal="Find a wireless audio product",
        budget=15000,
        seller_id="seller_04",
        guardrails=True,
    )
    assert outcome.allowed is False
    assert outcome.scenario.refusal_rule == "GR-9"
    assert outcome.razorpay_order_id is None
    assert fake.created == []


def test_allow_path_creates_razorpay_order_and_settles_on_confirm():
    gateway, fake = _gateway()
    outcome = gateway.authorize(
        goal="Find a wireless audio product",
        budget=15000,
        seller_id="seller_04",
        guardrails=False,
    )
    assert outcome.allowed is True
    assert outcome.razorpay_order_id is not None
    assert len(fake.created) == 1
    assert fake.created[0].external_id == outcome.razorpay_order_id

    payment_id = "pay_fake_1"
    signature = fake.sign_payment(outcome.razorpay_order_id, payment_id)
    settled = gateway.confirm_client_payment(outcome.razorpay_order_id, payment_id, signature)
    assert settled["ok"] is True
    assert settled["state"] == "SETTLED"
    order = gateway.state.db.get_order(outcome.kavach_order_id)
    assert order.state.value == "SETTLED"
    ref = gateway.state.db.get_payment_ref_by_external(outcome.razorpay_order_id)
    assert ref["status"] == "CAPTURED"


def test_webhook_capture_settles_order():
    gateway, fake = _gateway()
    outcome = gateway.authorize(
        goal="Find a wireless audio product",
        budget=15000,
        seller_id="seller_04",
        guardrails=False,
    )
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh_1",
                    "order_id": outcome.razorpay_order_id,
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = fake.sign_webhook(raw)
    result = gateway.handle_webhook(raw, sig, payload)
    assert result["state"] == "SETTLED"


def test_fastapi_health_and_authorize_refuse():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    app = create_app(cfg, gateway=CheckoutGateway(state))
    client = TestClient(app)
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/demo/pay"
    fav = client.get("/favicon.ico")
    assert fav.status_code == 200
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["payment_rail"] == "razorpay"

    refused = client.post(
        "/v1/checkout/authorize",
        json={"seller_id": "seller_04", "guardrails": True, "budget": 15000},
    )
    assert refused.status_code == 200
    body = refused.json()
    assert body["allowed"] is False
    assert body["refusal_rule"] == "GR-9"
    assert fake.created == []


def test_demo_pay_page_renders():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    app = create_app(cfg, gateway=CheckoutGateway(state))
    client = TestClient(app)
    page = client.get("/demo/pay")
    assert page.status_code == 200
    assert "Guardrail checkout" in page.text
    assert "kernel decides if money moves" in page.text
    assert "Authorize checkout" in page.text
    assert "Marketplace" in page.text
    assert "modeMarket" in page.text
    assert "Command Center" in page.text
    assert "viewFloor" in page.text
    assert "viewChat" in page.text
    assert 'data-view="floor"' in page.text
    assert "talkPane" in page.text
    assert "data-inspect=\"vault\"" in page.text
    assert "data-inspect=\"catalog\"" in page.text
    assert 'id="inspect"' in page.text
    css = client.get("/static/floor.css")
    js = client.get("/static/floor.js")
    assert css.status_code == 200
    assert js.status_code == 200


def test_floor_roster_has_per_agent_properties():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    app = create_app(cfg, gateway=CheckoutGateway(state))
    client = TestClient(app)
    floor = client.get("/v1/floor", params={"seller_id": "seller_04", "guardrails": "on"})
    assert floor.status_code == 200
    body = floor.json()
    ids = [agent["id"] for agent in body["agents"]]
    assert ids == ["buyer", "seller", "kernel", "llm"]
    seller = next(agent for agent in body["agents"] if agent["id"] == "seller")
    assert seller["sections"]["goal"]["current"] == "Bait and switch"
    assert seller["hire_id"] == "seller_04"
    kernel = next(agent for agent in body["agents"] if agent["id"] == "kernel")
    assert kernel["can_move_money"] is True
    assert kernel["sections"]["runtime"]["writes_db"].startswith("yes")
    buyer = next(agent for agent in body["agents"] if agent["id"] == "buyer")
    assert buyer["can_move_money"] is False
    assert set(buyer["sections"]) == {"identity", "goal", "runtime", "skills", "autonomy"}
    assert body["hired_seller_id"] == "seller_04"
    world = body["world"]
    assert "catalog" in world["stations"]
    assert "vault" in world["stations"]
    assert "mailbox" in world["stations"]
    assert "board" in world["stations"]
    assert "home" in world["stations"]
    assert "reviews" in world["stations"]
    assert world["stations"]["advisor"]["floor_brief"]
    assert len(world["stations"]["catalog"]["items"]) >= 1
    assert "review_snippets" in world["stations"]["catalog"]["items"][0]
    assert world["stations"]["catalog"]["items"][0]["reviews"] >= 2
    assert world["stations"]["reviews"]["items"]
    assert world["stations"]["vault"]["wallet_minor"] > 0
    assert world["stations"]["kernel"]["rules"]


def test_authorize_fills_mailbox_and_audit_board():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    gateway = CheckoutGateway(state)
    app = create_app(cfg, gateway=gateway)
    client = TestClient(app)
    refused = client.post(
        "/v1/checkout/authorize",
        json={"seller_id": "seller_04", "guardrails": True, "budget": 15000},
    )
    assert refused.status_code == 200
    assert refused.json()["allowed"] is False
    floor = client.get("/v1/floor", params={"seller_id": "seller_04", "guardrails": "on"})
    world = floor.json()["world"]
    assert world["stations"]["mailbox"]["messages"]
    assert world["stations"]["board"]["events"]
    assert world["last_run"]["refusal_rule"] == "GR-9"


def test_market_shop_settles_one_winner_and_creates_one_razorpay_order():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    gateway = CheckoutGateway(state)
    payload = gateway.shop_market(goal="Find a wireless audio product", budget=15000, guardrails=True)
    assert payload["allowed"] is True
    assert payload["stalls_visited"] == 5
    assert payload["winner"]["seller_id"].startswith("market_")
    assert payload["got_best_deal"] is True
    assert payload["razorpay_order_id"] is not None
    assert len(fake.created) == 1
    orders = state.db.conn.execute("SELECT seller_id, state FROM orders").fetchall()
    assert len(orders) == 1
    assert orders[0]["seller_id"] == payload["winner"]["seller_id"]
    assert orders[0]["state"] == "AUTHORIZED"


def test_floor_market_mode_lists_merchants_not_attack_sellers():
    fake = FakeRazorpayRail()
    cfg = _config()
    state = build_gateway_state(cfg, rail=fake)
    app = create_app(cfg, gateway=CheckoutGateway(state))
    client = TestClient(app)
    sellers = client.get("/v1/sellers").json()["sellers"]
    assert all(not row["id"].startswith("market_") for row in sellers)
    merchants = client.get("/v1/merchants").json()["merchants"]
    assert [row["id"] for row in merchants] == [
        "market_01",
        "market_02",
        "market_03",
        "market_04",
        "market_05",
    ]
    floor = client.get("/v1/floor", params={"mode": "market", "guardrails": "on"})
    body = floor.json()
    assert body["mode"] == "market"
    assert [row["id"] for row in body["merchants"]] == [row["id"] for row in merchants]
    catalog = body["world"]["stations"]["catalog"]["items"]
    assert {item.get("seller") for item in catalog} >= {
        "Harbor Goods",
        "Northline Mart",
        "Pulse Depot",
        "Ridge Exchange",
        "Ember Stall",
    }
    assert all(not row["id"].startswith("market_") for row in body["sellers"])
