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
    assert "Guardrail Gateway" in page.text
    assert "Authorize checkout" in page.text
