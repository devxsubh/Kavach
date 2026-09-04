"""Office-floor roster: each Kavach actor as a desk with its own file.

Inspired by Munder Difflin's hive (identity, goal, runtime, skills, autonomy)
but mapped onto Kavach's buyer / seller / kernel / LLM split — the kernel is
the only desk that can move money.
"""

from __future__ import annotations

from typing import Any

from ..adversarial.attacks import ATTACKS
from ..config import KavachConfig
from ..kernel.policy import RULES
from ..models import Buyer, Seller

ATTACK_BY_ID = {attack.attack_id: attack for attack in ATTACKS}

DEFAULT_GOAL = "Find a wireless audio product"
DEFAULT_BUDGET = 15000


def _money(minor: int) -> str:
    return f"${minor / 100:,.2f}"


def _attack_blurb(attack_class: str | None) -> dict[str, Any]:
    if not attack_class:
        return {
            "id": None,
            "name": "Honest counterparty",
            "mechanism": "Quotes fairly and never injects instructions.",
            "blocked_by": [],
        }
    attack = ATTACK_BY_ID.get(attack_class)
    if not attack:
        return {"id": attack_class, "name": attack_class, "mechanism": "", "blocked_by": []}
    return {
        "id": attack.attack_id,
        "name": attack.name,
        "mechanism": attack.mechanism,
        "blocked_by": list(attack.blocked_by),
    }


def seller_card(seller: Seller) -> dict[str, Any]:
    attack = _attack_blurb(seller.attack_class)
    return {
        "id": seller.id,
        "name": seller.name,
        "attack_class": seller.attack_class,
        "is_adversarial": seller.is_adversarial,
        "policy_profile": seller.policy_profile,
        "price_floor_pct": seller.price_floor_pct,
        "reputation_seed": seller.reputation_seed,
        "attack_name": attack["name"],
        "attack_mechanism": attack["mechanism"],
        "blocked_by": attack["blocked_by"],
        "label": f"{seller.id} · {attack['name']}",
    }


def _chip(status: str, label: str) -> dict[str, str]:
    return {"status": status, "label": label}


def buyer_desk(buyer: Buyer, *, goal: str, budget: int, llm_on: bool) -> dict[str, Any]:
    return {
        "id": "buyer",
        "seat": "desk-buyer",
        "name": buyer.name,
        "title": "Buyer",
        "accent": "sky",
        "archetype": "scientist",
        "status": _chip("idle", "idle"),
        "can_move_money": False,
        "blurb": "Shops inside a signed Intent mandate. Proposes — never settles.",
        "sections": {
            "identity": {
                "who": f"{buyer.name} ({buyer.id})",
                "role": "Shopper with a locked budget and hard constraints",
                "pubkey": buyer.pubkey[:18] + "…",
            },
            "goal": {
                "current": goal,
                "budget": _money(budget),
                "wallet": _money(buyer.wallet_balance_minor),
                "max_items": "1",
            },
            "runtime": {
                "engine": "IntentAgent + BuyerNegotiator",
                "llm": "optional JSON advice, then clamped" if llm_on else "deterministic rules only",
                "writes_db": "never",
            },
            "skills": [
                "parse natural-language intent",
                "search the catalog",
                "register a candidate set",
                "negotiate signed OFFER envelopes",
                "build a cart mandate",
            ],
            "autonomy": {
                "leash": "Cannot debit the wallet. Offers are clamped to budget and burst limits.",
                "escalates_to": "kernel",
                "human_gate": "GR-12 for large payments",
            },
        },
        "properties": [
            ("id", buyer.id),
            ("wallet", _money(buyer.wallet_balance_minor)),
            ("budget", _money(budget)),
            ("writes db", "no"),
        ],
    }


def seller_desk(seller: Seller) -> dict[str, Any]:
    attack = _attack_blurb(seller.attack_class)
    vibe = "Honest merchant" if not seller.is_adversarial else f"Red-team · {attack['id']}"
    return {
        "id": "seller",
        "seat": "desk-seller",
        "name": seller.name.split("(")[0].strip(),
        "title": "Seller",
        "accent": "coral" if seller.is_adversarial else "peach",
        "archetype": "hacker" if seller.is_adversarial else "cat-villager",
        "status": _chip("idle", "idle"),
        "can_move_money": False,
        "blurb": attack["mechanism"],
        "hire_id": seller.id,
        "sections": {
            "identity": {
                "who": seller.name,
                "role": vibe,
                "policy": seller.policy_profile,
            },
            "goal": {
                "current": attack["name"],
                "mechanism": attack["mechanism"],
                "blocked_by": ", ".join(attack["blocked_by"]) or "—",
            },
            "runtime": {
                "engine": "PricingAgent + SellerNegotiator",
                "llm": "never — templated quotes only",
                "writes_db": "never",
            },
            "skills": [
                "quote from list price and floor",
                "counter with signed COUNTER envelopes",
                "run one attack class when hired",
            ],
            "autonomy": {
                "leash": "Cannot settle. Checkout price is bound by GR-9 when rails are on.",
                "price_floor": f"{int(seller.price_floor_pct * 100)}% of list",
                "reputation": f"{seller.reputation_seed:.2f}",
            },
        },
        "properties": [
            ("id", seller.id),
            ("attack", attack["id"] or "clean"),
            ("policy", seller.policy_profile),
            ("floor", f"{int(seller.price_floor_pct * 100)}%"),
        ],
    }


def kernel_desk(*, guardrails: bool) -> dict[str, Any]:
    armed = "armed" if guardrails else "disarmed"
    return {
        "id": "kernel",
        "seat": "desk-kernel",
        "name": "Kernel",
        "title": "Guardrail kernel",
        "accent": "lemon",
        "archetype": "wizard",
        "status": _chip("idle", "idle") if guardrails else _chip("ghost", "disarmed"),
        "can_move_money": True,
        "blurb": "The only desk that can move money. GOD of this floor.",
        "sections": {
            "identity": {
                "who": "GuardrailKernel",
                "role": "Orchestrator / payment authority",
                "office": "You brief this desk — not the twelve sellers",
            },
            "goal": {
                "current": "Authorize checkout only after GR-1…GR-12",
                "mode": f"guardrails {armed}",
            },
            "runtime": {
                "engine": "firewall · mandates · holds · policy",
                "llm": "never in the path to a DB write",
                "writes_db": "yes — only after deterministic checks",
            },
            "skills": [f"{code}  {label}" for code, label in RULES.items()],
            "autonomy": {
                "leash": "Human still owns spend, scope, and destructive ops (GR-12).",
                "hold": "Wallet hold before debit — no check-then-spend races",
                "audit": "Append-only hash chain, replayable",
            },
        },
        "properties": [
            ("rails", "ON" if guardrails else "OFF"),
            ("moves money", "yes"),
            ("rules", "GR-1 … GR-12"),
            ("rail", "after allow only"),
        ],
    }


def llm_desk(config: KavachConfig) -> dict[str, Any]:
    on = config.use_llm
    return {
        "id": "llm",
        "seat": "desk-llm",
        "name": "Advisor",
        "title": "LLM advisor",
        "accent": "lilac",
        "archetype": "astronaut",
        "status": _chip("idle", "idle") if on else _chip("ghost", "offline"),
        "can_move_money": False,
        "blurb": "Suggests JSON. Validators clamp it. Never writes the world.",
        "sections": {
            "identity": {
                "who": config.llm_label,
                "role": "Advisory only — not a merchant, not a cashier",
            },
            "goal": {
                "current": "Draft IntentMandate and NegotiationDecision as JSON",
            },
            "runtime": {
                "engine": config.llm_backend if on else "off",
                "model": config.llm_model if on else "—",
                "writes_db": "never — hard invariant",
            },
            "skills": [
                "parse shopping goal → IntentDraft",
                "suggest offer / accept / walk",
                "short rationale string",
            ],
            "autonomy": {
                "leash": "Output is Pydantic-validated and price-clamped. Garbage → deterministic fallback.",
                "forbidden": "orders, ledger rows, bypassing GR-9",
            },
        },
        "properties": [
            ("mode", "ON" if on else "OFF"),
            ("backend", config.llm_backend if on else "rules"),
            ("model", config.llm_model if on else "—"),
            ("writes db", "no"),
        ],
    }


def build_floor(
    *,
    config: KavachConfig,
    buyer: Buyer,
    sellers: list[Seller],
    seller_id: str = "seller_04",
    goal: str = DEFAULT_GOAL,
    budget: int = DEFAULT_BUDGET,
    guardrails: bool | None = None,
) -> dict[str, Any]:
    rails = config.guardrails if guardrails is None else guardrails
    hired = next((s for s in sellers if s.id == seller_id), sellers[0] if sellers else None)
    if hired is None:
        raise ValueError(f"unknown seller {seller_id}")
    agents = [
        buyer_desk(buyer, goal=goal, budget=budget, llm_on=config.use_llm),
        seller_desk(hired),
        kernel_desk(guardrails=rails),
        llm_desk(config),
    ]
    return {
        "goal": goal,
        "budget_minor": budget,
        "budget": _money(budget),
        "guardrails": rails,
        "payment_rail": config.payment_rail,
        "payment_label": config.payment_label,
        "llm": config.llm_label,
        "hired_seller_id": hired.id,
        "agents": agents,
        "sellers": [seller_card(s) for s in sellers],
        "stations": [
            {"id": "catalog", "name": "Catalog shelf", "purpose": "discovery / candidate set"},
            {"id": "mailbox", "name": "Mailbox", "purpose": "signed OFFER / COUNTER envelopes"},
            {"id": "vault", "name": "Vault", "purpose": "hold → authorize → settle"},
            {"id": "board", "name": "Audit board", "purpose": "append-only event chain"},
        ],
    }
