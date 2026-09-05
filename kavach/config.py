from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from .exceptions import ConfigError

LlmBackend = Literal["anthropic", "ollama"]
PaymentRail = Literal["simulated", "razorpay"]
ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5"
ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"
OLLAMA_DEFAULT_MODEL = "llama3.2"
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_LOADED = False


def load_env_file() -> None:
    """Load `.env` from the project root if present."""
    global _ENV_LOADED
    if _ENV_LOADED or os.getenv("KAVACH_SKIP_DOTENV"):
        return
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    _ENV_LOADED = True


def _env(name: str, default: str | None = None) -> str | None:
    """Read a Kavach environment variable."""
    return os.getenv(name, default)


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class KavachConfig:
    guardrails: bool
    use_llm: bool
    llm_backend: LlmBackend
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None
    ollama_host: str
    budget_burst_pct: float
    strict_config: bool
    payment_rail: PaymentRail = "simulated"
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    @classmethod
    def from_env(cls) -> KavachConfig:
        load_env_file()
        burst_raw = _env("KAVACH_BUDGET_BURST_PCT", "0.15") or "0.15"
        try:
            budget_burst_pct = float(burst_raw)
        except ValueError as exc:
            raise ConfigError(f"KAVACH_BUDGET_BURST_PCT must be a float, got {burst_raw!r}") from exc
        if not 0 < budget_burst_pct <= 1:
            raise ConfigError(f"KAVACH_BUDGET_BURST_PCT must be in (0, 1], got {budget_burst_pct}")

        use_ollama = _truthy(_env("KAVACH_USE_OLLAMA"))
        # An explicit KAVACH_USE_LLM wins, so `KAVACH_USE_LLM=0` can switch the LLM off
        # without having to unset the backend selection too.
        use_llm_raw = _env("KAVACH_USE_LLM")
        use_llm = _truthy(use_llm_raw) if use_llm_raw is not None else use_ollama
        backend_raw = (_env("KAVACH_LLM_BACKEND", "ollama" if use_ollama else "anthropic") or "anthropic").lower()
        if backend_raw not in {"anthropic", "ollama"}:
            raise ConfigError(f"KAVACH_LLM_BACKEND must be 'anthropic' or 'ollama', got {backend_raw!r}")
        backend: LlmBackend = backend_raw  # type: ignore[assignment]

        api_key = os.getenv("ANTHROPIC_API_KEY") or _env("KAVACH_LLM_API_KEY")
        ollama_host = os.getenv("OLLAMA_HOST", OLLAMA_DEFAULT_HOST).rstrip("/")
        if backend == "anthropic":
            llm_model = _env("KAVACH_MODEL", ANTHROPIC_DEFAULT_MODEL) or ANTHROPIC_DEFAULT_MODEL
            llm_base_url = (_env("KAVACH_LLM_BASE_URL", ANTHROPIC_DEFAULT_BASE_URL) or ANTHROPIC_DEFAULT_BASE_URL).rstrip("/")
        else:
            llm_model = _env("KAVACH_MODEL", OLLAMA_DEFAULT_MODEL) or OLLAMA_DEFAULT_MODEL
            llm_base_url = ollama_host

        rail_raw = (_env("KAVACH_PAYMENT_RAIL", "simulated") or "simulated").lower()
        if rail_raw not in {"simulated", "razorpay"}:
            raise ConfigError(f"KAVACH_PAYMENT_RAIL must be 'simulated' or 'razorpay', got {rail_raw!r}")
        payment_rail: PaymentRail = rail_raw  # type: ignore[assignment]

        return cls(
            guardrails=os.getenv("GUARDRAILS", "on").lower() not in {"off", "0", "false"},
            use_llm=use_llm,
            llm_backend=backend,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key=api_key,
            ollama_host=ollama_host,
            budget_burst_pct=budget_burst_pct,
            strict_config=_truthy(_env("KAVACH_STRICT_CONFIG")),
            payment_rail=payment_rail,
            razorpay_key_id=os.getenv("RAZORPAY_KEY_ID") or None,
            razorpay_key_secret=os.getenv("RAZORPAY_KEY_SECRET") or None,
            razorpay_webhook_secret=os.getenv("RAZORPAY_WEBHOOK_SECRET") or None,
        )

    def validate_llm(self, available: bool) -> list[str]:
        warnings: list[str] = []
        if not self.use_llm:
            if self.strict_config:
                if _env("KAVACH_MODEL"):
                    raise ConfigError("KAVACH_MODEL is set but KAVACH_USE_LLM is disabled.")
                if os.getenv("ANTHROPIC_API_KEY") or _env("KAVACH_LLM_API_KEY"):
                    raise ConfigError("ANTHROPIC_API_KEY is set but KAVACH_USE_LLM is disabled.")
            return warnings
        if self.llm_backend == "anthropic" and not self.llm_api_key:
            message = (
                "KAVACH_USE_LLM is enabled with the Anthropic backend but ANTHROPIC_API_KEY is not set. "
                "Deterministic agents and validators will be used instead."
            )
            if self.strict_config:
                raise ConfigError(message)
            warnings.append(message)
            return warnings
        if self.llm_backend == "ollama" and not available:
            message = (
                f"KAVACH_USE_OLLAMA is enabled but Ollama is unreachable at {self.ollama_host}. "
                "Deterministic agents and validators will be used instead."
            )
            if self.strict_config:
                raise ConfigError(message)
            warnings.append(message)
        return warnings

    def validate_payment_rail(self) -> list[str]:
        """Return warnings (or raise in strict mode) when Razorpay is misconfigured."""
        warnings: list[str] = []
        if self.payment_rail != "razorpay":
            return warnings
        if not self.razorpay_key_id or not self.razorpay_key_secret:
            message = (
                "KAVACH_PAYMENT_RAIL=razorpay but RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are missing. "
                "Use test keys from the Razorpay dashboard."
            )
            if self.strict_config:
                raise ConfigError(message)
            warnings.append(message)
        return warnings

    @property
    def llm_label(self) -> str:
        if not self.use_llm:
            return "OFF (deterministic validators)"
        return f"ON ({self.llm_backend}: {self.llm_model})"

    @property
    def payment_label(self) -> str:
        if self.payment_rail == "razorpay":
            return "razorpay (test)"
        return "simulated ledger"
