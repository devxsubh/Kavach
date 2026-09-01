from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Operator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    LTE = "lte"
    GTE = "gte"
    IN = "in"
    CONTAINS = "contains"


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute: str = Field(min_length=1)
    operator: Operator
    value: Any


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute: str = Field(min_length=1)
    value: Any
    weight: float = Field(default=1.0, ge=0, le=1)


class IntentMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent_id: str = Field(default_factory=lambda: new_id("intent"))
    buyer_id: str
    goal_text: str = Field(min_length=1)
    budget_ceiling_minor: int = Field(gt=0)
    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_preferences: list[Preference] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    max_items: int = Field(default=1, gt=0)
    requires_human_approval_above_minor: int = Field(default=0, ge=0)
    expires_at: datetime = Field(default_factory=lambda: now_utc() + timedelta(minutes=30))


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    seller_id: str
    unit_price_minor: int = Field(gt=0)
    qty: int = Field(gt=0)


class CartMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cart_id: str = Field(default_factory=lambda: new_id("cart"))
    parent_intent_id: str
    lines: list[CartLine] = Field(min_length=1)
    total_minor: int = Field(gt=0)
    negotiation_transcript_hash: str = Field(min_length=1)
    expires_at: datetime = Field(default_factory=lambda: now_utc() + timedelta(minutes=5))

    @field_validator("total_minor")
    @classmethod
    def total_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("cart total must be positive")
        return value


class PaymentMandate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_id: str = Field(default_factory=lambda: new_id("payment"))
    parent_cart_id: str
    amount_minor: int = Field(gt=0)
    buyer_id: str
    idempotency_key: str = Field(min_length=8)
    human_approval_ref: str | None = None


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    seller_id: str
    title: str
    description: str
    list_price_minor: int = Field(gt=0)
    stock: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class Seller(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    policy_profile: str
    price_floor_pct: float = Field(gt=0, le=1)
    reputation_seed: float = Field(default=0.5, ge=0, le=1)
    pubkey: str
    is_adversarial: bool = False
    attack_class: str | None = None


class Buyer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    wallet_balance_minor: int = Field(ge=0)
    pubkey: str


class OrderState(str, Enum):
    DRAFT = "DRAFT"
    RESERVED = "RESERVED"
    AUTHORIZED = "AUTHORIZED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    REFUSED = "REFUSED"


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    buyer_id: str
    seller_id: str
    product_id: str
    unit_price_minor: int = Field(gt=0)
    qty: int = Field(gt=0)
    cart_mandate_id: str
    payment_mandate_id: str | None = None
    state: OrderState = OrderState.DRAFT
    idempotency_key: str
    created_at: datetime = Field(default_factory=now_utc)


class OfferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    price_minor: int = Field(gt=0)
    qty: int = Field(default=1, gt=0)
    text: str = ""


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    msg_id: str = Field(default_factory=lambda: new_id("msg"))
    conversation_id: str
    seq: int = Field(ge=0)
    sender_id: str
    recipient_id: str
    type: Literal["OFFER", "COUNTER", "ACCEPT", "REJECT", "QUERY", "INFORM"]
    payload: OfferPayload | dict[str, Any]
    trust: Literal["trusted", "untrusted"] = "untrusted"
    ts: datetime = Field(default_factory=now_utc)
    prev_hash: str = "GENESIS"
    signature: str = ""


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int
    ts: datetime = Field(default_factory=now_utc)
    actor: str
    event_type: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class CandidateSet(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    session_id: str


class StoryStep(BaseModel):
    """One human-readable beat in a demo negotiation."""
    model_config = ConfigDict(extra="forbid")
    phase: str
    title: str
    detail: str = ""


class ScenarioResult(BaseModel):
    scenario_id: str
    guardrails: bool
    attack_class: str | None
    settled: bool
    attack_succeeded: bool
    refusal_rule: str | None = None
    spent_minor: int = 0
    audit_replay_ok: bool = False
    clean_success: bool = False
    goal_text: str = ""
    budget_ceiling_minor: int = 0
    product_title: str = ""
    product_id: str = ""
    llm_used: bool = False
    order_id: str | None = None
    story: list[StoryStep] = Field(default_factory=list)
