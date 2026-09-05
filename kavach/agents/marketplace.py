"""Exclusive marketplace sim: one buyer shops every honest stall, kernel settles the winner.

Attack-floor scenarios stay untouched. This run is comparison shopping — same
product families at different merchants, free-will haggling, then GOD (kernel)
moves money only for the best closed deal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import KavachConfig
from ..kernel.core import satisfies_constraint
from ..models import CartLine, CartMandate, Product, ScenarioResult, StoryStep
from ..signing import KeyPair, digest
from ..world import Database
from ..world.replay import replay_order
from ..world.seed import is_market_seller
from .conversation_eval import attach_conversation_eval
from .orchestrator import IntentAgent, KavachRun, _money


class StallOffer(BaseModel):
    seller_id: str
    seller_name: str
    product_id: str = ""
    product_title: str = ""
    family: str = ""
    list_price_minor: int = 0
    negotiated_minor: int = 0
    accepted: bool = False
    walked: bool = False
    policy_profile: str = ""
    notes: str = ""


class MarketResult(BaseModel):
    scenario_id: str
    guardrails: bool
    goal_text: str
    budget_ceiling_minor: int
    stalls_visited: int
    stalls: list[StallOffer] = Field(default_factory=list)
    winner: StallOffer | None = None
    next_best: StallOffer | None = None
    got_best_deal: bool = False
    savings_vs_list_minor: int = 0
    savings_vs_next_minor: int = 0
    summary: str = ""
    settled: bool = False
    refusal_rule: str | None = None
    spent_minor: int = 0
    order_id: str | None = None
    llm_used: bool = False
    conversation_score: float = 1.0
    conversation_findings: list[str] = Field(default_factory=list)
    story: list[StoryStep] = Field(default_factory=list)
    attack_class: str | None = None
    product_title: str = ""
    product_id: str = ""


def _family(product: Product) -> str:
    return str((product.attributes or {}).get("family") or product.title.split(" (")[0])


def market_merchants(db: Database) -> list:
    from ..models import Seller

    rows = db.conn.execute("SELECT id FROM sellers ORDER BY id").fetchall()
    sellers: list[Seller] = []
    for row in rows:
        if is_market_seller(row["id"]):
            sellers.append(db.get_seller(row["id"]))
    return sellers


class MarketplaceRun:
    def __init__(
        self,
        db: Database,
        keys: dict[str, KeyPair],
        *,
        guardrails: bool = True,
        config: KavachConfig | None = None,
        payment_rail: str = "simulated",
    ):
        self.db = db
        self.keys = keys
        self.guardrails = guardrails
        self.config = config or KavachConfig.from_env()
        self.payment_rail = payment_rail
        self.runner = KavachRun(
            db, keys, guardrails=guardrails, config=self.config, payment_rail=payment_rail
        )

    def run(
        self,
        goal_text: str = "Find a wireless audio product",
        budget: int = 15000,
        scenario_id: str = "market",
        *,
        settle: bool = True,
        talk_seed: int | None = None,
    ) -> MarketResult:
        merchants = market_merchants(self.db)
        llm_on = bool(self.runner.llm and self.runner.llm.available())
        talk_mode = "LLM talk" if llm_on else "rules talk"
        story: list[StoryStep] = [
            StoryStep(
                phase="setup",
                title="1. Buyer enters the marketplace",
                detail=(
                    f'Goal: "{goal_text}" · Max budget: {_money(budget)} · '
                    f"Stalls: {len(merchants)} · Talk: {talk_mode} · "
                    "GOD (kernel) watches; money does not move until the comparison is done."
                ),
            )
        ]
        intent = IntentAgent(self.runner.llm).parse("buyer_01", goal_text, budget)
        cats = ", ".join(intent.allowed_categories) or "any"
        story.append(StoryStep(
            phase="intent",
            title="2. Intent locked for the whole market",
            detail=f"Categories: {cats} · Buyer will visit every matching stall and keep the best handshake.",
        ))

        stalls: list[StallOffer] = []
        llm_used = False
        seed = talk_seed if talk_seed is not None else 11
        for index, seller in enumerate(merchants):
            probe = self.runner.run(
                goal_text=goal_text,
                budget=budget,
                seller_id=seller.id,
                scenario_id=f"{scenario_id}:{seller.id}",
                checkout=False,
                talk_seed=seed + index * 17,
            )
            llm_used = llm_used or probe.llm_used
            product = self.db.get_product(probe.product_id) if probe.product_id else None
            accepted = probe.negotiated_minor > 0
            walked = any(step.phase == "walk" for step in probe.story) or (
                not accepted and any(step.phase == "fail" for step in probe.story)
            )
            offer = StallOffer(
                seller_id=seller.id,
                seller_name=seller.name,
                product_id=probe.product_id,
                product_title=probe.product_title,
                family=_family(product) if product else "",
                list_price_minor=product.list_price_minor if product else 0,
                negotiated_minor=probe.negotiated_minor,
                accepted=accepted,
                walked=walked,
                policy_profile=seller.policy_profile,
                notes="handshake" if accepted else ("walked" if walked else "no match"),
            )
            stalls.append(offer)
            story.append(StoryStep(
                phase="discovery",
                title=f"Stall {index + 1}: {seller.name}",
                detail=(
                    f"Policy {seller.policy_profile} · floor {int(seller.price_floor_pct * 100)}% · "
                    + (f'{offer.product_title} list {_money(offer.list_price_minor)}' if offer.product_title else "no matching SKU")
                ),
            ))
            for step in probe.story:
                if step.phase in {"setup", "intent"}:
                    continue
                story.append(StoryStep(
                    phase=step.phase,
                    title=f"{seller.name} · {step.title}",
                    detail=step.detail,
                ))

        accepted = [stall for stall in stalls if stall.accepted]
        winner = min(accepted, key=lambda stall: (stall.negotiated_minor, stall.seller_id)) if accepted else None
        same_family = [stall for stall in accepted if winner and stall.family == winner.family]
        peers = same_family or accepted
        next_best = None
        if winner and len(peers) > 1:
            rest = [stall for stall in peers if stall.seller_id != winner.seller_id]
            if rest:
                next_best = min(rest, key=lambda stall: stall.negotiated_minor)
        got_best = bool(winner) and winner.negotiated_minor == min((stall.negotiated_minor for stall in peers), default=winner.negotiated_minor)
        cheaper_unclosed = []
        if winner:
            cheaper_unclosed = [
                stall for stall in stalls
                if stall.family == winner.family
                and not stall.accepted
                and stall.list_price_minor
                and stall.list_price_minor < winner.negotiated_minor
            ]
        savings_list = (winner.list_price_minor - winner.negotiated_minor) if winner else 0
        savings_next = (next_best.negotiated_minor - winner.negotiated_minor) if winner and next_best else 0

        summary = _summarize(
            stalls=stalls,
            winner=winner,
            next_best=next_best,
            got_best=got_best,
            cheaper_unclosed=cheaper_unclosed,
            savings_list=savings_list,
            savings_next=savings_next,
        )
        story.append(StoryStep(phase="compare", title="GOD compares the table", detail=summary))

        result = MarketResult(
            scenario_id=scenario_id,
            guardrails=self.guardrails,
            goal_text=goal_text,
            budget_ceiling_minor=budget,
            stalls_visited=len(stalls),
            stalls=stalls,
            winner=winner,
            next_best=next_best,
            got_best_deal=got_best,
            savings_vs_list_minor=max(0, savings_list),
            savings_vs_next_minor=max(0, savings_next),
            summary=summary,
            llm_used=llm_used,
            story=story,
            product_title=winner.product_title if winner else "",
            product_id=winner.product_id if winner else "",
        )
        if winner is None:
            story.append(StoryStep(phase="fail", title="No stall would meet the buyer", detail="Marketplace closed without a handshake."))
            result.story = story
            return result
        return self._settle_winner(result, winner, goal_text, budget, settle=settle)

    def _settle_winner(
        self,
        result: MarketResult,
        winner: StallOffer,
        goal_text: str,
        budget: int,
        *,
        settle: bool,
    ) -> MarketResult:
        buyer_id = "buyer_01"
        intent = IntentAgent(self.runner.llm).parse(buyer_id, goal_text, budget)
        signed_intent = self.runner.authority.issue(intent, buyer_id)
        product = self.db.get_product(winner.product_id)
        session_id = f"{result.scenario_id}:checkout"
        self.runner.kernel.register_candidates(session_id, [product])
        if intent.hard_constraints and self.guardrails:
            if not all(satisfies_constraint(product, constraint) for constraint in intent.hard_constraints):
                result.story.append(StoryStep(
                    phase="refuse",
                    title="Kernel refused the market winner",
                    detail="GR-7: winning SKU failed a locked constraint.",
                ))
                result.refusal_rule = "GR-7"
                return result
        cart = CartMandate(
            parent_intent_id=intent.intent_id,
            lines=[CartLine(
                product_id=winner.product_id,
                seller_id=winner.seller_id,
                unit_price_minor=winner.negotiated_minor,
                qty=1,
            )],
            total_minor=winner.negotiated_minor,
            negotiation_transcript_hash=digest({
                "market": result.scenario_id,
                "seller": winner.seller_id,
                "product": winner.product_id,
                "price": winner.negotiated_minor,
            }),
        )
        signed_cart = self.runner.authority.issue(cart, buyer_id, parent_id=intent.intent_id)
        result.story.append(StoryStep(
            phase="checkout",
            title="Winner goes to GOD",
            detail=(
                f"{winner.seller_name} · {winner.product_title} · "
                f"{_money(winner.negotiated_minor)}. Kernel is the only desk that can settle."
            ),
        ))
        try:
            self.runner.kernel.verify_cart(
                session_id,
                signed_intent,
                signed_cart,
                committed_prices={winner.product_id: winner.negotiated_minor},
            )
            order = self.runner.kernel.reserve_stock(session_id, signed_cart, buyer_id=buyer_id)
            payment = self.runner.kernel.issue_payment(signed_intent, signed_cart, buyer_id)
            order = self.runner.kernel.authorize_payment(session_id, signed_intent, signed_cart, payment, order)
            result.order_id = order.id
            if not settle:
                result.story.append(StoryStep(
                    phase="checkout",
                    title="Authorized — awaiting capture",
                    detail=f"Order {order.id} held. Razorpay may open next.",
                ))
                return result
            order = self.runner.kernel.settle_order(order)
            result.settled = True
            result.spent_minor = winner.negotiated_minor
            result.story.append(StoryStep(
                phase="done",
                title="Market order settled",
                detail=f"Paid {_money(winner.negotiated_minor)} to {winner.seller_name}. Replay OK: {replay_order(self.db, order.id)}",
            ))
        except Exception as exc:
            rule = getattr(exc, "rule_id", None)
            result.refusal_rule = rule
            result.story.append(StoryStep(
                phase="refuse",
                title="Kernel refused the market winner",
                detail=f"{rule or 'error'}: {exc}",
            ))
        scored = attach_conversation_eval(ScenarioResult(
            scenario_id=result.scenario_id,
            guardrails=result.guardrails,
            attack_class=None,
            settled=result.settled,
            attack_succeeded=False,
            refusal_rule=result.refusal_rule,
            spent_minor=result.spent_minor,
            goal_text=result.goal_text,
            budget_ceiling_minor=result.budget_ceiling_minor,
            product_title=result.product_title,
            product_id=result.product_id,
            seller_id=winner.seller_id,
            negotiated_minor=winner.negotiated_minor,
            llm_used=result.llm_used,
            story=result.story,
        ))
        result.conversation_score = scored.conversation_score
        result.conversation_findings = scored.conversation_findings
        return result


def _summarize(
    *,
    stalls: list[StallOffer],
    winner: StallOffer | None,
    next_best: StallOffer | None,
    got_best: bool,
    cheaper_unclosed: list[StallOffer],
    savings_list: int,
    savings_next: int,
) -> str:
    lines = [f"Visited {len(stalls)} stalls. Closed {sum(s.accepted for s in stalls)} handshakes."]
    for stall in stalls:
        if stall.accepted:
            lines.append(
                f"- {stall.seller_name}: {stall.product_title} listed {_money(stall.list_price_minor)} → "
                f"closed {_money(stall.negotiated_minor)} ({stall.policy_profile})"
            )
        elif stall.product_title:
            lines.append(
                f"- {stall.seller_name}: {stall.product_title} listed {_money(stall.list_price_minor)} → {stall.notes}"
            )
        else:
            lines.append(f"- {stall.seller_name}: {stall.notes}")
    if not winner:
        lines.append("Best deal: none — no stall met the buyer.")
        return "\n".join(lines)
    lines.append(
        f"Winner: {winner.seller_name} at {_money(winner.negotiated_minor)} "
        f"(saved {_money(max(0, savings_list))} vs their list)."
    )
    if next_best:
        lines.append(
            f"Next-best closed: {next_best.seller_name} at {_money(next_best.negotiated_minor)} "
            f"({_money(savings_next)} more)."
        )
    if cheaper_unclosed:
        names = ", ".join(f"{s.seller_name} list {_money(s.list_price_minor)}" for s in cheaper_unclosed)
        lines.append(f"Cheaper list prices that never closed: {names}.")
    lines.append("Best closed deal: yes." if got_best else "Best closed deal: no — a cheaper handshake was left on the table.")
    return "\n".join(lines)
