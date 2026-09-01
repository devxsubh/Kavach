from __future__ import annotations

from .advanced_models import IntentDraft, NegotiationDecision
from .exceptions import GuardrailViolation
from .models import Constraint, IntentMandate


def validate_intent_draft(draft: IntentDraft, *, budget_ceiling_minor: int) -> IntentDraft:
    if draft.max_items < 1:
        raise GuardrailViolation("GR-7", "intent max_items must be at least 1")
    constraints: list[dict[str, object]] = []
    for raw in draft.hard_constraints:
        constraint = Constraint.model_validate(raw)
        constraints.append(constraint.model_dump(mode="python"))
    return draft.model_copy(update={"hard_constraints": constraints, "max_items": min(draft.max_items, 20)})


def mandate_from_draft(buyer_id: str, goal_text: str, budget: int, draft: IntentDraft) -> IntentMandate:
    validated = validate_intent_draft(draft, budget_ceiling_minor=budget)
    constraints = [Constraint.model_validate(item) for item in validated.hard_constraints]
    return IntentMandate(
        buyer_id=buyer_id,
        goal_text=goal_text,
        budget_ceiling_minor=budget,
        hard_constraints=constraints,
        allowed_categories=validated.allowed_categories,
        max_items=validated.max_items,
        requires_human_approval_above_minor=budget + 1,
    )


def enforce_budget_burst(previous_offer: int, proposed_offer: int, budget_ceiling_minor: int, *, burst_pct: float) -> int:
    max_step = max(1, int(budget_ceiling_minor * burst_pct))
    capped = min(proposed_offer, budget_ceiling_minor)
    if capped <= previous_offer:
        return max(1, capped)
    return min(capped, previous_offer + max_step)


def validate_negotiation_decision(
    decision: NegotiationDecision,
    *,
    reservation: int,
    budget_ceiling_minor: int,
    previous_offer: int,
    burst_pct: float,
) -> NegotiationDecision:
    if decision.action == "walk":
        return decision
    price = decision.price_minor
    if price is None:
        return decision
    if price > budget_ceiling_minor:
        price = budget_ceiling_minor
    if price > reservation:
        price = reservation
    price = enforce_budget_burst(previous_offer, price, budget_ceiling_minor, burst_pct=burst_pct)
    return decision.model_copy(update={"price_minor": max(1, price)})


def deterministic_intent_draft(goal_text: str) -> IntentDraft:
    constraints: list[dict[str, object]] = []
    lowered = goal_text.lower()
    if "wireless" in lowered:
        constraints.append({"attribute": "wireless", "operator": "eq", "value": True})
    category = next((c for c in ("kitchen", "audio", "office", "outdoor") if c in lowered), None)
    return IntentDraft(
        goal_text=goal_text,
        hard_constraints=constraints,
        allowed_categories=[category] if category else [],
        max_items=1,
    )
