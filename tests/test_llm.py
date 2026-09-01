from kavach.agents.orchestrator import BuyerNegotiator, IntentAgent
from kavach.advanced_models import IntentDraft, NegotiationDecision
from kavach.config import KavachConfig
from kavach.models import IntentMandate


class FakeLLM:
    def __init__(self):
        self.calls = []

    def available(self):
        return True

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        if schema is IntentDraft:
            return IntentDraft(goal_text="Find audio", allowed_categories=["audio"])
        return NegotiationDecision(action="offer", price_minor=999999, rationale="over ceiling")


def test_intent_llm_output_is_typed():
    llm = FakeLLM()
    mandate = IntentAgent(llm).parse("b", "Find an audio product", 5000)
    assert isinstance(mandate, IntentMandate)
    assert mandate.allowed_categories == ["audio"]


def test_negotiation_llm_output_is_clamped():
    llm = FakeLLM()
    config = KavachConfig(
        guardrails=True,
        use_llm=False,
        llm_backend="nvidia",
        llm_model="deepseek-ai/deepseek-v4-flash-0731",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key=None,
        ollama_host="http://127.0.0.1:11434",
        budget_burst_pct=0.15,
        strict_config=False,
    )
    decision = BuyerNegotiator(kernel=None, buyer_id="b", llm=llm, config=config).decision(
        IntentMandate(buyer_id="b", goal_text="audio", budget_ceiling_minor=5000),
        "seller data",
        10,
        100,
        seller_price=80,
        round_no=0,
    )
    assert decision.price_minor == 100
