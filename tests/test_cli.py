from kavach.adversarial.attacks import ATTACKS
from kavach.cli import main


def run_cli(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["kavach", *argv])
    monkeypatch.setenv("KAVACH_USE_LLM", "0")
    return main()


def test_demo_accepts_goal_budget_and_seller(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["demo", "--plain", "--goal", "Find a kitchen product", "--budget", "9000", "--seller", "seller_02", "--guardrails", "on"]) == 0
    out = capsys.readouterr().out
    assert "Find a kitchen product" in out
    assert "$90.00" in out
    assert "seller_02" in out
    assert "ON" in out
    assert "What happened" in out
    assert "Result" in out


def test_demo_guardrails_flag_overrides_env(monkeypatch, capsys):
    monkeypatch.setenv("GUARDRAILS", "on")
    assert run_cli(monkeypatch, ["demo", "--plain", "--guardrails", "off"]) == 0
    out = capsys.readouterr().out
    assert "OFF" in out


def test_demo_rejects_unknown_seller(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["demo", "--plain", "--seller", "seller_99"]) == 2
    err_out = capsys.readouterr()
    combined = err_out.out + err_out.err
    assert "unknown seller" in combined
    assert "kavach sellers" in combined


def test_sellers_lists_attack_classes(monkeypatch, capsys):
    assert run_cli(monkeypatch, ["sellers", "--plain"]) == 0
    out = capsys.readouterr().out
    assert "seller_01" in out
    assert "seller_04" in out
    assert "Bait and switch" in out


def test_budget_extraction_attack_maps_to_untrusted_text_rules():
    a5 = next(a for a in ATTACKS if a.attack_id == "A-5")
    assert "GR-5" not in a5.blocked_by
    assert set(a5.blocked_by) == {"GR-1", "GR-2"}
