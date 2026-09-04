from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from ..config import KavachConfig

T = TypeVar("T", bound=BaseModel)

_SCHEMA_EXAMPLES: dict[str, str] = {
    "IntentDraft": (
        '{"goal_text":"Find a wireless audio product","hard_constraints":'
        '[{"attribute":"wireless","operator":"eq","value":true}],'
        '"allowed_categories":["audio"],"max_items":1}'
    ),
    "NegotiationDecision": (
        '{"action":"offer","price_minor":1200,"rationale":"incremental counter",'
        '"utterance":"I can stretch to $12.00 — can you meet me there?"}'
    ),
    "SellerQuote": (
        '{"price_minor":1400,"utterance":"Closest I can get today is $14.00 on that unit."}'
    ),
}


class LLMResponseError(ValueError):
    pass


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _looks_like_json_schema(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    return "properties" in data and "type" in data and not any(key in data for key in ("goal_text", "action", "product_ids"))


def _parse_schema_response(text: str, schema: type[T]) -> T:
    cleaned = _extract_json(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("model returned invalid JSON") from exc
    if _looks_like_json_schema(payload):
        raise LLMResponseError("model returned JSON Schema instead of data")
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseError("model JSON did not match expected shape") from exc


def _schema_prompt(system: str, schema: type[T]) -> str:
    example = _SCHEMA_EXAMPLES.get(schema.__name__, "{}")
    return (
        f"{system}\n\n"
        "Return one JSON object with DATA values only.\n"
        "Do NOT return JSON Schema. Never use keys like type, properties, or definitions.\n"
        f"Example: {example}"
    )


class LLMAdapter:
    """Optional LLM adapter (Nvidia DeepSeek by default, Ollama as fallback). Kernel remains authoritative."""

    def __init__(self, config: KavachConfig):
        self.config = config
        self._client = None

    @property
    def backend(self) -> str:
        return self.config.llm_backend

    @property
    def model(self) -> str:
        return self.config.llm_model

    def available(self) -> bool:
        if not self.config.use_llm:
            return False
        if self.config.llm_backend == "nvidia":
            return bool(self.config.llm_api_key)
        return self._ollama_reachable()

    def generate_json(self, system: str, user: str, schema: type[T]) -> T:
        if self.config.llm_backend == "nvidia":
            return self._generate_nvidia(system, user, schema)
        return self._generate_ollama(system, user, schema)

    def _client_for_nvidia(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.config.llm_base_url, api_key=self.config.llm_api_key)
        return self._client

    def _generate_nvidia(self, system: str, user: str, schema: type[T]) -> T:
        client = self._client_for_nvidia()
        completion = client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": _schema_prompt(system, schema)},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            top_p=0.95,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
        return _parse_schema_response(content, schema)

    def _generate_ollama(self, system: str, user: str, schema: type[T]) -> T:
        payload = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": _schema_prompt(system, schema)},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1},
        }
        request = urllib.request.Request(
            f"{self.config.ollama_host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read())
        except urllib.error.URLError as exc:
            raise LLMResponseError(f"Ollama request failed: {exc}") from exc
        message = body.get("message") or {}
        content = message.get("content") or body.get("response") or ""
        if not content:
            raise LLMResponseError("Ollama returned an empty response")
        return _parse_schema_response(content, schema)

    def _ollama_reachable(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.config.ollama_host}/api/tags", timeout=0.5) as response:
                return response.status == 200
        except Exception:
            return False
