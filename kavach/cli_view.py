"""Terminal rendering helpers for the Kavach CLI."""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .models import ScenarioResult

PHASE_STYLE = {
    "intent": "cyan",
    "discovery": "cyan",
    "negotiate": "yellow",
    "agree": "green",
    "checkout": "magenta",
    "done": "bold green",
    "refuse": "bold red",
    "walk": "yellow",
    "fail": "red",
}


def make_console(*, plain: bool = False) -> Console:
    if plain:
        return Console(force_terminal=False, no_color=True, highlight=False, width=100)
    return Console(highlight=False, soft_wrap=True)


def money(minor: int) -> str:
    return f"${minor / 100:,.2f}"


def _outcome(result: ScenarioResult) -> tuple[str, str, str]:
    if result.settled and result.attack_succeeded:
        return "ATTACK SUCCEEDED", "bold white on red", "The adversarial seller got paid despite the buyer's intent."
    if result.settled:
        return "ORDER SETTLED", "bold white on green", "Checkout cleared the guardrail kernel and the audit trail replayed cleanly."
    if result.refusal_rule:
        return f"REFUSED · {result.refusal_rule}", "bold white on dark_orange", "The kernel blocked checkout before money moved."
    return "NO DEAL", "bold white on grey37", "Negotiation ended without a settled order."


def print_banner(console: Console, *, goal: str, budget: int, seller_id: str, seller_label: str, guardrails: bool, llm_label: str) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()
    table.add_row("Goal", escape(goal))
    table.add_row("Budget", f"{money(budget)}  [dim]({budget} minor units)[/]")
    table.add_row("Seller", f"{escape(seller_id)}  [dim]{escape(seller_label)}[/]")
    table.add_row("Guardrails", "[green]ON[/]" if guardrails else "[red]OFF[/]")
    table.add_row("LLM", escape(llm_label))
    console.print()
    console.print(Panel(table, title="[bold]Kavach demo[/]", subtitle="one buyer ↔ one seller", border_style="bright_blue"))


def print_story(console: Console, result: ScenarioResult) -> None:
    tree = Tree("[bold]What happened[/]")
    for step in result.story:
        style = PHASE_STYLE.get(step.phase, "white")
        node = tree.add(Text(step.title, style=style))
        if step.detail:
            for line in step.detail.splitlines():
                node.add(Text(line, style="dim"))

    console.print()
    console.print(tree)


def print_result(console: Console, result: ScenarioResult) -> None:
    title, style, blurb = _outcome(result)
    header = Text(title, style=style)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()
    table.add_row("Product", result.product_title or "(none)")
    table.add_row("Spent", f"{money(result.spent_minor)} of {money(result.budget_ceiling_minor)} budget")
    table.add_row("Seller", result.attack_class or "clean / honest")
    table.add_row("Guardrails", "ON" if result.guardrails else "OFF")
    table.add_row("LLM", "helped" if result.llm_used else "rules only")
    table.add_row("Attack won", "yes" if result.attack_succeeded else "no")
    table.add_row("Audit replay", "ok" if result.audit_replay_ok else "broken")
    if result.refusal_rule:
        table.add_row("Refused by", result.refusal_rule)

    console.print()
    console.print(Panel(Group(header, Text(blurb, style="dim"), Text(""), table), title="Result", border_style="green" if result.settled and not result.attack_succeeded else ("red" if result.attack_succeeded or result.refusal_rule else "grey50")))


def print_audit(console: Console, events: list[Any], *, limit: int = 8) -> None:
    if not events:
        return
    table = Table(title="Kernel audit (recent)", show_lines=False, box=None, padding=(0, 1))
    table.add_column("#", style="dim", justify="right")
    table.add_column("Event")
    table.add_column("Detail", style="dim")
    for event in events[-limit:]:
        payload = event.payload or {}
        detail = payload.get("rule_id") or payload.get("order_id") or payload.get("label") or ""
        table.add_row(f"{event.seq:03d}", event.event_type, str(detail))
    console.print()
    console.print(table)


def print_tips(console: Console, *, seller_id: str, guardrails: bool) -> None:
    console.print()
    console.print(Rule(style="dim"))
    console.print("[dim]Try next:[/]")
    flip = "off" if guardrails else "on"
    console.print(f"  [cyan]uv run kavach demo --guardrails {flip} --seller {escape(seller_id)}[/]")
    console.print("  [cyan]uv run kavach sellers[/]")
    console.print("  [cyan]uv run kavach tui[/]   [dim](press R)[/]")
    console.print()


def print_sellers(console: Console, sellers: list[Any], attack_lookup: dict[str, Any]) -> None:
    table = Table(title="Demo sellers", show_lines=False, expand=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Attack")
    table.add_column("What they try")
    table.add_column("Blocked by", style="dim")
    for seller in sellers:
        if seller.attack_class and seller.attack_class in attack_lookup:
            attack = attack_lookup[seller.attack_class]
            table.add_row(seller.id, seller.name, f"{attack.attack_id} · {attack.name}", attack.mechanism, ", ".join(attack.blocked_by))
        else:
            table.add_row(seller.id, seller.name, "—", "Honest counterparty", "—")
    console.print()
    console.print(table)
    console.print("[dim]Example:[/] [cyan]uv run kavach demo --seller seller_04 --guardrails on[/]")
    console.print("[dim]Then flip:[/] [cyan]uv run kavach demo --seller seller_04 --guardrails off[/]")
    console.print()


def print_eval_summary(console: Console, scorecard: dict[str, Any], *, md_path: str, json_path: str) -> None:
    table = Table(title="Evaluation scorecard", show_header=True)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    interesting = [
        ("scenarios", "Scenarios"),
        ("attack_success_rate_guardrails_off", "Attack success · OFF"),
        ("attack_success_rate_guardrails_on", "Attack success · ON"),
        ("clean_task_completion_rate", "Clean completion"),
        ("budget_ceiling_breaches", "Budget breaches"),
        ("unbacked_purchases", "Unbacked purchases"),
        ("audit_replay_rate", "Audit replay rate"),
        ("refusal_rate_guardrails_on", "Refusal rate · ON"),
    ]
    for key, label in interesting:
        value = scorecard.get(key)
        if isinstance(value, float):
            rendered = f"{value:.1%}" if "rate" in key else f"{value:.4f}"
        else:
            rendered = str(value)
        style = "green" if key.endswith("_on") and isinstance(value, float) and value == 0 else None
        table.add_row(label, Text(rendered, style=style))

    console.print()
    console.print(table)

    by_attack = scorecard.get("by_attack_class") or {}
    if by_attack:
        attacks = Table(title="Per-attack", show_lines=False)
        attacks.add_column("Attack")
        attacks.add_column("Off", justify="right")
        attacks.add_column("On", justify="right")
        attacks.add_column("Refusals", justify="right")
        for attack_id, row in by_attack.items():
            attacks.add_row(
                attack_id,
                f"{row['success_rate_off']:.0%}",
                f"{row['success_rate_on']:.0%}",
                str(row["refusals_on"]),
            )
        console.print()
        console.print(attacks)

    console.print()
    console.print(f"[green]Wrote[/] {md_path}")
    console.print(f"[green]Wrote[/] {json_path}")
    console.print()
