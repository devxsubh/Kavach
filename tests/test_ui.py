import pytest

from kavach.ui import KavachTUI


@pytest.mark.asyncio
async def test_tui_mounts_core_panes():
    app = KavachTUI()
    async with app.run_test() as pilot:
        assert app.query_one("#agent-log")
        assert app.query_one("#negotiation-log")
        assert app.query_one("#guardrail-log")
        assert app.query_one("#config")
        assert app.query_one("#outcome")
        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_cycles_seller_and_toggles_guardrails(monkeypatch):
    monkeypatch.setenv("KAVACH_USE_LLM", "0")
    app = KavachTUI()
    async with app.run_test() as pilot:
        start_index = app.seller_index
        app.action_cycle_seller()
        assert app.seller_index == (start_index + 1) % len(app.sellers)
        before = app.guardrails_on
        app.action_toggle_guardrails()
        assert app.guardrails_on is (not before)
        await pilot.pause()
