from __future__ import annotations

import time
from dataclasses import dataclass

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static

from ..adversarial.attacks import ATTACKS
from ..agents import KavachRun
from ..agents.roster import DEFAULT_BUDGET, DEFAULT_GOAL, build_floor
from ..config import KavachConfig
from ..models import ScenarioResult, StoryStep
from ..signing import KeyPair
from ..world import Database, seed_world


@dataclass(frozen=True)
class SellerChoice:
    seller_id: str
    label: str
    attack_id: str | None


def _seller_choices() -> list[SellerChoice]:
    choices = [SellerChoice("seller_01", "Honest counterparty", None)]
    for i, attack in enumerate(ATTACKS, start=2):
        choices.append(SellerChoice(f"seller_{i:02d}", attack.name, attack.attack_id))
    return choices


PHASE_GLYPH = {
    "setup": ("›", "cyan"),
    "intent": ("›", "cyan"),
    "discovery": ("›", "cyan"),
    "negotiate": ("↔", "yellow"),
    "agree": ("✓", "green"),
    "checkout": ("⬡", "#c084fc"),
    "done": ("✓", "bold green"),
    "refuse": ("✕", "bold red"),
    "walk": ("↺", "yellow"),
    "fail": ("—", "red"),
}

AUDIT_PLAIN = {
    "CANDIDATE_SET": "Products shortlisted",
    "FIREWALL_SCAN": "Scanned untrusted text",
    "STOCK_RESERVED": "Reserved stock",
    "FUNDS_HELD": "Funds held",
    "PAYMENT_AUTHORIZED": "Wallet debit authorized",
    "ORDER_SETTLED": "Order completed",
    "GUARDRAIL_REFUSAL": "Blocked unsafe action",
    "PAYMENT_REPLAY_NOOP": "Duplicate payment ignored",
    "ESCALATION_REQUESTED": "Human approval requested",
}


def _money(minor: int) -> str:
    return f"${minor / 100:,.2f}"


def _outcome(result: ScenarioResult) -> tuple[str, str, str]:
    if result.settled and result.attack_succeeded:
        return "ATTACK SUCCEEDED", "Seller got paid past the buyer's intent.", "outcome-attack"
    if result.settled:
        return "ORDER SETTLED", "Checkout cleared the kernel.", "outcome-ok"
    if result.refusal_rule:
        return f"REFUSED · {result.refusal_rule}", "Kernel blocked checkout before money moved.", "outcome-refuse"
    return "NO DEAL", "Negotiation ended without a settled order.", "outcome-idle"


class KavachTUI(App[None]):
    TITLE = "Kavach"
    SUB_TITLE = "guardrail checkout · kernel decides"
    CSS = """
    Screen {
        background: #1A1320;
        color: #FFF8E7;
    }
    Header {
        background: #1A1320;
        color: #F4E9C7;
        dock: top;
        height: 1;
    }
    Footer {
        background: #1A1320;
        color: #A899B5;
    }
    #chrome {
        height: 7;
        margin: 0 1;
        layout: vertical;
    }
    #config {
        height: 3;
        padding: 0 2;
        content-align: left middle;
        background: #3D2E4A;
        border-left: tall #FFD93D;
        color: #FFF8E7;
    }
    #outcome {
        height: 3;
        margin-top: 1;
        padding: 0 2;
        content-align: left middle;
        background: #3D2E4A;
        border-left: tall #A899B5;
        color: #A899B5;
    }
    #outcome.outcome-idle { border-left: tall #A899B5; color: #A899B5; }
    #outcome.outcome-ok { border-left: tall #6BCF7F; color: #B4E5BD; }
    #outcome.outcome-refuse { border-left: tall #FFD93D; color: #FFEC99; }
    #outcome.outcome-attack { border-left: tall #FF6B6B; color: #FFB4B4; }
    #main {
        height: 1fr;
        padding: 1 1 0 1;
    }
    .pane {
        background: #2A2033;
        border: round #6B5878;
        margin-right: 1;
        padding: 0 0 1 0;
    }
    #cast { width: 30%; }
    #story { width: 42%; }
    #kernel { width: 28%; margin-right: 0; }
    .pane-title {
        height: 1;
        margin: 0 0 1 0;
        padding: 0 2;
        background: #3D2E4A;
        color: #FFD93D;
        text-style: bold;
    }
    RichLog {
        height: 1fr;
        background: #2A2033;
        scrollbar-size: 1 1;
        padding: 0 1;
        overflow-x: hidden;
    }
    """
    BINDINGS = [
        Binding("r", "run_scenario", "Run", show=True, priority=True),
        Binding("g", "toggle_guardrails", "Guardrails", show=True, priority=True),
        Binding("s", "cycle_seller", "Seller", show=True, priority=True),
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.sellers = _seller_choices()
        self.seller_index = next((i for i, s in enumerate(self.sellers) if s.attack_id == "A-3"), 0)
        self._config = KavachConfig.from_env()
        self.guardrails_on = self._config.guardrails
        self._scenario_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="chrome"):
            yield Static(id="config")
            yield Static("Ready — press [bold]R[/] to run.", id="outcome", classes="outcome-idle", markup=True)
        with Horizontal(id="main"):
            with Vertical(classes="pane", id="cast"):
                yield Static(" FLOOR", classes="pane-title")
                yield RichLog(id="agent-log", markup=True, wrap=True, auto_scroll=True)
            with Vertical(classes="pane", id="story"):
                yield Static(" STORY", classes="pane-title")
                yield RichLog(id="negotiation-log", markup=True, wrap=True, auto_scroll=True)
            with Vertical(classes="pane", id="kernel"):
                yield Static(" KERNEL", classes="pane-title")
                yield RichLog(id="guardrail-log", markup=True, wrap=True, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        for log_id in ("agent-log", "negotiation-log", "guardrail-log"):
            self.query_one(f"#{log_id}", RichLog).can_focus = False
        self._refresh_config()
        self._write_idle_panes()

    def _seller(self) -> SellerChoice:
        return self.sellers[self.seller_index]

    def _set_outcome_class(self, css: str) -> None:
        outcome = self.query_one("#outcome", Static)
        for name in ("outcome-idle", "outcome-ok", "outcome-refuse", "outcome-attack"):
            outcome.set_class(name == css, name)

    def _refresh_config(self) -> None:
        seller = self._seller()
        attack = seller.attack_id or "clean"
        rails = "[bold #6BCF7F]ON[/]" if self.guardrails_on else "[bold #FF6B6B]OFF[/]"
        self.query_one("#config", Static).update(
            f"[bold]{seller.seller_id}[/]  ·  {seller.label}  ·  [cyan]{attack}[/]"
            f"     Guardrails {rails}"
            f"     Budget [bold]$150[/]"
            f"     LLM [dim]{self._config.llm_label}[/]"
        )

    def _kv(self, log: RichLog, key: str, value: str) -> None:
        log.write(f"  [dim]{key:<8}[/] {value}")

    def _floor_roster(self, result: ScenarioResult | None = None) -> dict:
        db = Database(":memory:")
        buyer, sellers = seed_world(db, products_per_seller=1)
        floor = build_floor(
            config=self._config,
            buyer=buyer,
            sellers=sellers,
            seller_id=self._seller().seller_id,
            goal=result.goal_text if result else DEFAULT_GOAL,
            budget=result.budget_ceiling_minor if result else DEFAULT_BUDGET,
            guardrails=result.guardrails if result else self.guardrails_on,
        )
        db.close()
        return floor

    def _write_agent_card(self, log: RichLog, agent: dict) -> None:
        color = {
            "sky": "#4ECDC4",
            "coral": "#FF6B6B",
            "lemon": "#FFD93D",
            "lilac": "#B197FC",
            "peach": "#FFA07A",
        }.get(agent["accent"], "#FFF8E7")
        status = agent["status"]["label"]
        log.write(f"[bold {color}]{agent['title']}[/]  [dim]{status}[/]")
        log.write(f"  [dim]{agent['blurb']}[/]")
        for key, value in agent["properties"]:
            self._kv(log, str(key), str(value))
        leash = agent["sections"]["autonomy"].get("leash")
        if leash:
            self._kv(log, "leash", leash)
        log.write("")

    def _write_idle_panes(self) -> None:
        agents = self.query_one("#agent-log", RichLog)
        story = self.query_one("#negotiation-log", RichLog)
        kernel = self.query_one("#guardrail-log", RichLog)
        agents.clear()
        story.clear()
        kernel.clear()
        seller = self._seller()
        floor = self._floor_roster()
        for agent in floor["agents"]:
            self._write_agent_card(agents, agent)

        story.write("[dim]No run yet.[/]")
        story.write("")
        story.write("  [bold]R[/]  negotiate this seller")
        story.write("  [bold]S[/]  next attack class")
        story.write("  [bold]G[/]  toggle guardrails")
        if seller.attack_id == "A-3":
            story.write("")
            story.write("[cyan]Best first demo[/]")
            story.write("  A-3 bait-and-switch — run ON, then OFF.")

        kernel.write("[dim]Audit trail waits for a run.[/]")
        kernel.write("")
        if self.guardrails_on:
            kernel.write("[#6BCF7F]● Guardrails armed[/]")
        else:
            kernel.write("[#FF6B6B]● Guardrails off — attacks can land[/]")
        kernel.write("")
        kernel.write("[dim]Kernel is the only desk that can move money.[/]")

    def action_toggle_guardrails(self) -> None:
        if self._scenario_running:
            return
        self.guardrails_on = not self.guardrails_on
        self._refresh_config()
        self._write_idle_panes()
        self._set_outcome_class("outcome-idle")
        state = "ON" if self.guardrails_on else "OFF"
        self.query_one("#outcome", Static).update(f"Guardrails [bold]{state}[/]. Press R to run.")

    def action_cycle_seller(self) -> None:
        if self._scenario_running:
            return
        self.seller_index = (self.seller_index + 1) % len(self.sellers)
        self._refresh_config()
        self._write_idle_panes()
        seller = self._seller()
        self._set_outcome_class("outcome-idle")
        tag = seller.attack_id or "clean"
        self.query_one("#outcome", Static).update(
            f"Seller → [bold]{seller.seller_id}[/] ([cyan]{tag}[/]). Press R to run."
        )

    def action_run_scenario(self) -> None:
        if self._scenario_running:
            return
        self._scenario_running = True
        for log_id in ("agent-log", "negotiation-log", "guardrail-log"):
            self.query_one(f"#{log_id}", RichLog).clear()
        self._set_outcome_class("outcome-idle")
        self.query_one("#outcome", Static).update("[yellow]Negotiating…[/]")
        self.query_one("#agent-log", RichLog).write("[dim]Buyer waking up…[/]")
        self.query_one("#negotiation-log", RichLog).write("[dim]Building story…[/]")
        self.query_one("#guardrail-log", RichLog).write("[dim]Kernel watching…[/]")
        self._run_in_background()

    @work(thread=True, exclusive=True)
    def _run_in_background(self) -> None:
        config = KavachConfig.from_env()
        self._config = config
        db = Database(":memory:")
        buyer, sellers = seed_world(db, products_per_seller=8)
        keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{seller.id: KeyPair() for seller in sellers}}
        seller = self._seller()
        result = KavachRun(db, keys, guardrails=self.guardrails_on, config=config).run(
            seller_id=seller.seller_id,
            scenario_id=f"tui_{seller.seller_id}",
        )
        events = db.audit_events()
        self.call_from_thread(self._render_cast, result, config.llm_label)
        self.call_from_thread(self._clear_story)
        for step in result.story:
            self.call_from_thread(self._append_story_step, step)
            time.sleep(0.07)
        self.call_from_thread(self._render_kernel, result, events)
        self.call_from_thread(self._render_outcome, result, config.llm_label)
        self.call_from_thread(self._refresh_config)
        db.close()
        self.call_from_thread(self._mark_idle)

    def _clear_story(self) -> None:
        self.query_one("#negotiation-log", RichLog).clear()

    def _mark_idle(self) -> None:
        self._scenario_running = False

    def _render_cast(self, result: ScenarioResult, llm_label: str) -> None:
        agents = self.query_one("#agent-log", RichLog)
        agents.clear()
        floor = self._floor_roster(result)
        for agent in floor["agents"]:
            if agent["id"] == "buyer":
                agent["properties"] = [
                    ("goal", result.goal_text or "—"),
                    ("budget", _money(result.budget_ceiling_minor)),
                    ("llm", "helped" if result.llm_used else "rules only"),
                    ("item", result.product_title or "—"),
                ]
            if agent["id"] == "llm":
                agent["properties"] = [
                    ("mode", "helped" if result.llm_used else "idle"),
                    ("backend", llm_label),
                    ("writes db", "no"),
                ]
            self._write_agent_card(agents, agent)

    def _append_story_step(self, step: StoryStep) -> None:
        story = self.query_one("#negotiation-log", RichLog)
        glyph, color = PHASE_GLYPH.get(step.phase, ("•", "white"))
        # Strip leading "1. " / "5b. " numbering noise for a cleaner rhythm.
        title = step.title
        if ". " in title[:4]:
            title = title.split(". ", 1)[-1]
        story.write(f"[{color}]{glyph} {title}[/]")
        if step.detail:
            for line in step.detail.splitlines():
                story.write(f"  [dim]{line}[/]")
        story.write("")

    def _render_kernel(self, result: ScenarioResult, events) -> None:
        kernel = self.query_one("#guardrail-log", RichLog)
        kernel.clear()
        if result.refusal_rule:
            kernel.write(f"[bold #FF6B6B]✕ Refused[/]  {result.refusal_rule}")
        elif result.settled and result.attack_succeeded:
            kernel.write("[bold #FF6B6B]✕ Attack landed[/]")
        elif result.settled:
            kernel.write("[bold #6BCF7F]✓ Checkout cleared[/]")
        else:
            kernel.write("[dim]— No checkout[/]")
        kernel.write("")
        kernel.write("[bold]Audit[/]")
        for event in events[-14:]:
            if event.event_type == "GUARDRAIL_REFUSAL":
                color = "#FF6B6B"
            elif event.event_type == "FIREWALL_SCAN" and not result.guardrails:
                color = "#A899B5"
            else:
                color = "#6BCF7F"
            label = AUDIT_PLAIN.get(event.event_type, event.event_type)
            payload = event.payload or {}
            detail = payload.get("rule_id") or payload.get("label") or ""
            suffix = f"  [dim]{detail}[/]" if detail else ""
            kernel.write(f"[{color}]{event.seq:02d}[/] {label}{suffix}")
        kernel.write("")
        replay = "[#6BCF7F]ok[/]" if result.audit_replay_ok else "[#FF6B6B]broken[/]"
        kernel.write(f"Replay {replay}   Spent [bold]{_money(result.spent_minor)}[/]")

    def _render_outcome(self, result: ScenarioResult, llm_label: str) -> None:
        title, blurb, css = _outcome(result)
        self._set_outcome_class(css)
        self.query_one("#outcome", Static).update(
            f"[bold]{title}[/]   {_money(result.spent_minor)} / {_money(result.budget_ceiling_minor)}"
            f"   attack {'yes' if result.attack_succeeded else 'no'}"
            f"   [dim]{blurb}[/]"
        )


def run_tui() -> None:
    KavachTUI().run()
