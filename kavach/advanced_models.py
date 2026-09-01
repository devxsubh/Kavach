from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    product_id: str
    author_id: str
    rating: int = Field(ge=1, le=5)
    body: str
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class EscalationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REFUSED = "REFUSED"
    TIMED_OUT = "TIMED_OUT"


class EscalationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    buyer_id: str
    seller_id: str
    amount_minor: int = Field(gt=0)
    reason: str
    expires_at: datetime = Field(default_factory=lambda: utc_now() + timedelta(seconds=30))
    status: EscalationStatus = EscalationStatus.PENDING
    approval_ref: str | None = None


class IntentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_text: str = Field(min_length=1, max_length=1000)
    hard_constraints: list[dict[str, object]] = Field(default_factory=list, max_length=12)
    allowed_categories: list[str] = Field(default_factory=list, max_length=5)
    max_items: int = Field(default=1, ge=1, le=20)


class NegotiationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["offer", "accept", "walk"]
    price_minor: int | None = Field(default=None, ge=1)
    rationale: str = Field(default="", max_length=500)


class DiscoveryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(default="", max_length=500)


class FirewallFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    label: str
    flagged: bool
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
