from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adversarial.attacks import ATTACKS
from .adversarial.evaluation import write_scorecard
from .cli_view import (
    make_console,
    print_audit,
    print_banner,
    print_eval_summary,
    print_market_result,
    print_result,
    print_sellers,
    print_story,
    print_tips,
)
from .config import KavachConfig
from .signing import KeyPair
from .world import Database, seed_world


EPILOG = """
examples:
  kavach demo
  kavach demo --seller seller_04 --guardrails on
  kavach sellers
  kavach tui
  kavach serve
  kavach market
  kavach eval --scenarios 40
"""


def _load_config() -> KavachConfig:
    return KavachConfig.from_env()


def _emit_config_warnings(config: KavachConfig, console) -> None:
    for warning in config.validate_payment_rail():
        console.print(f"[yellow]warning:[/] {warning}", soft_wrap=True)
    if not config.use_llm:
        return
    from .agents.llm import LLMAdapter

    adapter = LLMAdapter(config)
    for warning in config.validate_llm(adapter.available()):
        console.print(f"[yellow]warning:[/] {warning}", soft_wrap=True)


def _seller_label(seller) -> str:
    if seller.attack_class:
        attack = next((a for a in ATTACKS if a.attack_id == seller.attack_class), None)
        if attack:
            return f"{attack.attack_id} · {attack.name}"
        return seller.attack_class
    return "honest / clean"


def demo(args: argparse.Namespace) -> int:
    console = make_console(plain=args.plain)
    config = _load_config()
    _emit_config_warnings(config, console)
    guardrails = config.guardrails if args.guardrails is None else args.guardrails == "on"
    db = Database(":memory:")
    buyer, sellers = seed_world(db, products_per_seller=8)
    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    by_id = {s.id: s for s in sellers}
    if args.seller not in by_id:
        console.print(f"[red]error:[/] unknown seller {args.seller!r}", soft_wrap=True)
        console.print("[dim]Run[/] [cyan]kavach sellers[/] [dim]to see IDs like seller_01 … seller_09.[/]")
        db.close()
        return 2

    seller = by_id[args.seller]
    from .agents import KavachRun

    print_banner(
        console,
        goal=args.goal,
        budget=args.budget,
        seller_id=seller.id,
        seller_label=_seller_label(seller),
        guardrails=guardrails,
        llm_label=config.llm_label,
    )
    console.print("[dim]Negotiating…[/]")
    result = KavachRun(db, keys, guardrails=guardrails, config=config).run(
        goal_text=args.goal, budget=args.budget, seller_id=args.seller
    )
    print_story(console, result)
    print_result(console, result)
    print_audit(console, db.audit_events())
    print_tips(console, seller_id=args.seller, guardrails=guardrails)
    db.close()
    return 0


def market_cmd(args: argparse.Namespace) -> int:
    console = make_console(plain=args.plain)
    config = _load_config()
    _emit_config_warnings(config, console)
    guardrails = config.guardrails if args.guardrails is None else args.guardrails == "on"
    db = Database(":memory:")
    buyer, sellers = seed_world(db, products_per_seller=8)
    keys = {buyer.id: KeyPair(), "kernel": KeyPair(), **{s.id: KeyPair() for s in sellers}}
    from .agents.marketplace import MarketplaceRun

    print_banner(
        console,
        goal=args.goal,
        budget=args.budget,
        seller_id="marketplace",
        seller_label="five honest stalls · comparison shopping",
        guardrails=guardrails,
        llm_label=config.llm_label,
    )
    console.print("[dim]Buyer is walking every stall…[/]")
    result = MarketplaceRun(db, keys, guardrails=guardrails, config=config).run(
        goal_text=args.goal,
        budget=args.budget,
        talk_seed=args.seed,
    )
    print_story(console, result)
    print_market_result(console, result)
    print_audit(console, db.audit_events())
    db.close()
    return 0


def sellers_cmd(args: argparse.Namespace) -> int:
    console = make_console(plain=args.plain)
    db = Database(":memory:")
    _, sellers = seed_world(db, products_per_seller=1)
    lookup = {a.attack_id: a for a in ATTACKS}
    print_sellers(console, sellers, lookup)
    db.close()
    return 0


def eval_cmd(args: argparse.Namespace) -> int:
    console = make_console(plain=args.plain)
    console.print(f"[dim]Running {args.scenarios} scenarios × guardrails on/off…[/]")
    md, js = write_scorecard(args.output, seed=args.seed, scenarios=args.scenarios)
    scorecard = json.loads(Path(js).read_text())
    print_eval_summary(console, scorecard, md_path=str(md), json_path=str(js))
    return 0


def serve_cmd(args: argparse.Namespace) -> int:
    console = make_console(plain=args.plain)
    config = _load_config()
    _emit_config_warnings(config, console)
    console.print(f"[bold]Kavach Guardrail Gateway[/] on [cyan]http://{args.host}:{args.port}[/]")
    console.print(f"  Payment rail: {config.payment_label}")
    console.print(f"  Demo pay:     http://{args.host}:{args.port}/demo/pay")
    console.print(f"  Health:       http://{args.host}:{args.port}/health")
    from .api import run_server

    run_server(host=args.host, port=args.port)
    return 0


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plain", action="store_true", help="disable color / rich formatting")

    parser = argparse.ArgumentParser(
        prog="kavach",
        description="Kavach — adversarial multi-agent commerce with a deterministic guardrail kernel",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dm = sub.add_parser(
        "demo",
        parents=[common],
        help="run one buyer↔seller negotiation and print the story",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Tip: kavach sellers lists attack classes you can pass to --seller.",
    )
    dm.add_argument("--goal", default="Find a wireless audio product", help="what the buyer is shopping for")
    dm.add_argument("--budget", type=int, default=15000, metavar="CENTS", help="budget ceiling in minor units / cents (default: 15000 = $150)")
    dm.add_argument("--seller", default="seller_01", metavar="ID", help="seller id from `kavach sellers` (default: seller_01)")
    dm.add_argument("--guardrails", choices=("on", "off"), default=None, help="override GUARDRAILS env (on|off)")

    sub.add_parser("sellers", parents=[common], help="list demo sellers and their attack classes")
    mk = sub.add_parser("market", parents=[common], help="one buyer shops every honest stall and settles the best deal")
    mk.add_argument("--goal", default="Find a wireless audio product")
    mk.add_argument("--budget", type=int, default=15000, metavar="CENTS")
    mk.add_argument("--guardrails", choices=("on", "off"), default=None)
    mk.add_argument("--seed", type=int, default=11)
    sub.add_parser("tui", parents=[common], help="open the live 3-pane interface (press R to run, Q to quit)")

    srv = sub.add_parser("serve", parents=[common], help="run the FastAPI guardrail gateway (Razorpay-ready)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8080)

    ev = sub.add_parser("eval", parents=[common], help="run the guarded vs unguarded evaluation harness")
    ev.add_argument("--output", default="artifacts", help="directory for scorecard.md / scorecard.json")
    ev.add_argument("--seed", type=int, default=7)
    ev.add_argument("--scenarios", type=int, default=200, help="scenarios per guardrails mode")

    args = parser.parse_args()
    if args.command == "demo":
        return demo(args)
    if args.command == "sellers":
        return sellers_cmd(args)
    if args.command == "market":
        return market_cmd(args)
    if args.command == "tui":
        console = make_console(plain=args.plain)
        _emit_config_warnings(_load_config(), console)
        from .ui import run_tui

        run_tui()
        return 0
    if args.command == "serve":
        return serve_cmd(args)
    return eval_cmd(args)


if __name__ == "__main__":
    raise SystemExit(main())
