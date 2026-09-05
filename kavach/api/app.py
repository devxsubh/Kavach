from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..config import KavachConfig
from ..exceptions import GuardrailViolation
from .schemas import AuthorizeRequest, ClientPaymentConfirm, MarketShopRequest, ScenarioRunRequest
from .service import CheckoutGateway, build_gateway_state


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    config: KavachConfig | None = None,
    *,
    gateway: CheckoutGateway | None = None,
) -> FastAPI:
    config = config or KavachConfig.from_env()
    state = None
    if gateway is None:
        state = build_gateway_state(config)
        gateway = CheckoutGateway(state)
    app = FastAPI(title="Kavach Guardrail Gateway", version="0.1.0")
    app.state.gateway = gateway
    app.state.config = config

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def root():
        return RedirectResponse(url="/demo/pay", status_code=307)

    @app.get("/favicon.ico")
    @app.get("/favicon.svg")
    def favicon():
        path = STATIC_DIR / "favicon.svg"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="favicon missing")
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/health")
    def health():
        cfg: KavachConfig = app.state.config
        return {
            "ok": True,
            "payment_rail": cfg.payment_rail,
            "payment_label": cfg.payment_label,
            "guardrails_default": cfg.guardrails,
            "llm": cfg.llm_label,
        }

    @app.get("/v1/sellers")
    def sellers():
        return {"sellers": app.state.gateway.list_sellers()}

    @app.get("/v1/merchants")
    def merchants():
        return {"merchants": app.state.gateway.list_merchants()}

    @app.get("/v1/floor")
    def floor(
        seller_id: str = Query(default="seller_04"),
        goal: str = Query(default="Find a wireless audio product"),
        budget: int = Query(default=15000, gt=0),
        guardrails: str | None = Query(default=None),
        mode: str = Query(default="attack"),
    ):
        rails = None if guardrails is None else guardrails != "off"
        return app.state.gateway.list_floor(
            seller_id=seller_id,
            goal=goal,
            budget=budget,
            guardrails=rails,
            mode=mode if mode in {"attack", "market"} else "attack",
        )

    @app.post("/v1/scenarios/run")
    def run_scenario(body: ScenarioRunRequest):
        result = app.state.gateway.run_scenario(
            goal=body.goal,
            budget=body.budget,
            seller_id=body.seller_id,
            guardrails=body.guardrails,
        )
        return result.model_dump(mode="json")

    @app.post("/v1/market/shop")
    def shop_market(body: MarketShopRequest):
        return app.state.gateway.shop_market(
            goal=body.goal,
            budget=body.budget,
            guardrails=body.guardrails,
        )

    @app.post("/v1/checkout/authorize")
    def authorize(body: AuthorizeRequest):
        outcome = app.state.gateway.authorize(
            goal=body.goal,
            budget=body.budget,
            seller_id=body.seller_id,
            guardrails=body.guardrails,
        )
        status = 200 if outcome.allowed or outcome.scenario.refusal_rule else 200
        return JSONResponse(
            status_code=status,
            content={
                "allowed": outcome.allowed,
                "message": outcome.message,
                "refusal_rule": outcome.scenario.refusal_rule,
                "kavach_order_id": outcome.kavach_order_id,
                "amount_minor": outcome.amount_minor,
                "currency": outcome.currency,
                "razorpay_order_id": outcome.razorpay_order_id,
                "razorpay_key_id": outcome.razorpay_key_id,
                "attack_class": outcome.scenario.attack_class,
                "guardrails": outcome.scenario.guardrails,
                "product_title": outcome.scenario.product_title,
                "story": outcome.story,
            },
        )

    @app.post("/v1/checkout/confirm")
    def confirm(body: ClientPaymentConfirm):
        try:
            return app.state.gateway.confirm_client_payment(
                body.razorpay_order_id,
                body.razorpay_payment_id,
                body.razorpay_signature,
            )
        except GuardrailViolation as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/webhooks/razorpay")
    async def razorpay_webhook(
        request: Request,
        x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    ):
        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8"))
            return app.state.gateway.handle_webhook(body, x_razorpay_signature or "", payload)
        except GuardrailViolation as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc

    @app.get("/demo/pay", response_class=HTMLResponse)
    def demo_pay(
        seller_id: str = Query(default="seller_04"),
        guardrails: str = Query(default="on"),
    ):
        path = STATIC_DIR / "pay.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="pay.html missing")
        html = path.read_text(encoding="utf-8")
        html = html.replace("{{SELLER_ID}}", seller_id)
        html = html.replace("{{GUARDRAILS}}", "true" if guardrails != "off" else "false")
        return HTMLResponse(html)

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    import uvicorn

    config = KavachConfig.from_env()
    for warning in config.validate_payment_rail():
        print(f"warning: {warning}")
    if config.use_llm:
        from ..agents.llm import LLMAdapter

        adapter = LLMAdapter(config)
        for warning in config.validate_llm(adapter.available()):
            print(f"warning: {warning}")
    uvicorn.run(create_app(config), host=host, port=port, log_level="info")
