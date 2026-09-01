import json
from unittest.mock import MagicMock, patch

import pytest

from kavach.advanced_models import IntentDraft, NegotiationDecision
from kavach.agents.llm import LLMAdapter, LLMResponseError, _extract_json, _parse_schema_response
from kavach.config import KavachConfig, NVIDIA_DEFAULT_MODEL


def _config(**overrides):
    defaults = dict(
        guardrails=True,
        use_llm=True,
        llm_backend="nvidia",
        llm_model=NVIDIA_DEFAULT_MODEL,
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key="test-key",
        ollama_host="http://127.0.0.1:11434",
        budget_burst_pct=0.15,
        strict_config=False,
    )
    defaults.update(overrides)
    return KavachConfig(**defaults)


def test_extract_json_strips_markdown_fence():
    assert _extract_json("```json\n{\"goal_text\":\"x\"}\n```") == '{"goal_text":"x"}'


def test_nvidia_adapter_parses_structured_intent():
    adapter = LLMAdapter(_config())
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=json.dumps({"goal_text": "Find audio", "allowed_categories": ["audio"]})))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = completion
    with patch.object(adapter, "_client_for_nvidia", return_value=mock_client):
        draft = adapter.generate_json("system", "Find audio", IntentDraft)
    assert draft.allowed_categories == ["audio"]
    mock_client.chat.completions.create.assert_called_once()
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == NVIDIA_DEFAULT_MODEL


def test_nvidia_available_requires_api_key():
    assert LLMAdapter(_config(llm_api_key="test-key")).available() is True
    assert LLMAdapter(_config(llm_api_key=None)).available() is False


def test_parse_schema_response_rejects_json_schema_shape():
    schema_blob = json.dumps({"type": "object", "properties": {"goal_text": {"type": "string"}}, "definitions": {}})
    with pytest.raises(LLMResponseError, match="JSON Schema"):
        _parse_schema_response(schema_blob, IntentDraft)


def test_ollama_adapter_uses_chat_api():
    adapter = LLMAdapter(_config(use_llm=True, llm_backend="ollama", llm_model="llama3.2:1b"))
    response_body = json.dumps({"message": {"content": json.dumps({"goal_text": "Find audio", "allowed_categories": ["audio"]})}}).encode()
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = response_body
        draft = adapter.generate_json("system", "Find audio", IntentDraft)
    assert draft.allowed_categories == ["audio"]
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/api/chat")
