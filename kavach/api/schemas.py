from __future__ import annotations

from pydantic import BaseModel, Field


class ScenarioRunRequest(BaseModel):
    goal: str = "Find a wireless audio product"
    budget: int = Field(default=15000, gt=0)
    seller_id: str = "seller_01"
    guardrails: bool | None = None


class AuthorizeRequest(BaseModel):
    goal: str = "Find a wireless audio product"
    budget: int = Field(default=15000, gt=0)
    seller_id: str = "seller_04"
    guardrails: bool | None = None


class ClientPaymentConfirm(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
