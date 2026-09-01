import os

import pytest

from kavach.config import KavachConfig, NVIDIA_DEFAULT_MODEL
from kavach.exceptions import ConfigError
from kavach.validators import enforce_budget_burst, validate_intent_draft, validate_negotiation_decision
from kavach.advanced_models import IntentDraft, NegotiationDecision


def test_budget_burst_limits_offer_jump():
    assert enforce_budget_burst(100, 5000, 5000, burst_pct=0.15) == 850


def test_negotiation_validator_clamps_ceiling_and_burst():
    decision = NegotiationDecision(action="offer", price_minor=9999, rationale="too high")
    validated = validate_negotiation_decision(
        decision,
        reservation=3000,
        budget_ceiling_minor=5000,
        previous_offer=100,
        burst_pct=0.15,
    )
    assert validated.price_minor == 850


def test_intent_draft_validator_normalizes_constraints():
    draft = IntentDraft(goal_text="audio", hard_constraints=[{"attribute": "wireless", "operator": "eq", "value": True}])
    validated = validate_intent_draft(draft, budget_ceiling_minor=5000)
    assert validated.hard_constraints[0]["attribute"] == "wireless"


def test_strict_config_rejects_nvidia_without_api_key(monkeypatch):
    monkeypatch.setenv("KAVACH_USE_LLM", "1")
    monkeypatch.setenv("KAVACH_STRICT_CONFIG", "1")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("KAVACH_LLM_API_KEY", raising=False)
    config = KavachConfig.from_env()
    with pytest.raises(ConfigError, match="NVIDIA_API_KEY"):
        config.validate_llm(available=False)


def test_strict_config_rejects_ollama_without_server(monkeypatch):
    monkeypatch.delenv("KAVACH_USE_LLM", raising=False)
    monkeypatch.setenv("KAVACH_USE_OLLAMA", "1")
    monkeypatch.setenv("KAVACH_STRICT_CONFIG", "1")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:59999")
    config = KavachConfig.from_env()
    with pytest.raises(ConfigError, match="unreachable"):
        config.validate_llm(available=False)


def test_strict_config_rejects_unused_model_env(monkeypatch):
    monkeypatch.setenv("KAVACH_MODEL", NVIDIA_DEFAULT_MODEL)
    monkeypatch.setenv("KAVACH_STRICT_CONFIG", "1")
    monkeypatch.delenv("KAVACH_USE_LLM", raising=False)
    monkeypatch.delenv("KAVACH_USE_OLLAMA", raising=False)
    config = KavachConfig.from_env()
    with pytest.raises(ConfigError, match="KAVACH_MODEL"):
        config.validate_llm(available=False)
