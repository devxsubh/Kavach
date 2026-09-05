from kavach.agents.orchestrator import BuyerNegotiator, IntentAgent, SellerNegotiator
from kavach.advanced_models import IntentDraft, NegotiationDecision, SellerQuote
from kavach.config import KavachConfig
from kavach.models import IntentMandate, Product
from kavach.signing import KeyPair
from kavach.world import Database, seed_world


class FakeLLM:
    def __init__(self):
        self.calls = []

    def available(self):
        return True

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        if schema is IntentDraft:
            return IntentDraft(goal_text="Find audio", allowed_categories=["audio"])
        if schema is SellerQuote:
            return SellerQuote(price_minor=9000, utterance="I can do nine thousand cents on that unit.")
        return NegotiationDecision(
            action="offer",
            price_minor=999999,
            rationale="over ceiling",
            utterance="I'll go a bit higher — still under my limit.",
        )


def test_intent_llm_output_is_typed():
    llm = FakeLLM()
    mandate = IntentAgent(llm).parse("b", "Find an audio product", 5000)
    assert isinstance(mandate, IntentMandate)
    assert mandate.allowed_categories == ["audio"]


def test_negotiation_llm_output_is_clamped_and_keeps_utterance():
    llm = FakeLLM()
    config = KavachConfig(
        guardrails=True,
        use_llm=False,
        llm_backend="anthropic",
        llm_model="claude-haiku-4-5",
        llm_base_url="https://api.anthropic.com",
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
    assert "limit" in decision.utterance


def test_seller_llm_quote_uses_utterance():
    llm = FakeLLM()
    db = Database(":memory:")
    buyer, sellers = seed_world(db, seed=7, products_per_seller=2)
    from kavach.kernel import GuardrailKernel, MandateAuthority

    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    kernel = GuardrailKernel(db, MandateAuthority(keys), guardrails=True)
    seller = next(s for s in sellers if s.id == "seller_01")
    product = next(p for p in db.search_products() if p.seller_id == seller.id)
    neg = SellerNegotiator(db, kernel, seller.id, llm=llm, talk_seed=1)
    reply = neg.reply(product, buyer_offer=5000, round_no=0)
    assert neg.used_llm is True
    assert "nine thousand" in reply.text.lower() or reply.price_minor == 9000
    db.close()
