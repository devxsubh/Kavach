"""Story format the demo UI parses into live buyer/seller bubbles."""

from __future__ import annotations

import re

import pytest

from .helpers import AUDIO_GOAL, SELLERS, quote_count, run_scenario

BUYER_QUOTE = re.compile(r'Buyer: "([\s\S]*?)"')
SELLER_QUOTE = re.compile(r'Seller: "([\s\S]*?)"')
DECISION = re.compile(r"Buyer decision \(([^)]+)\): ([^\n]+)")


def messages_from_step(title: str, detail: str, phase: str) -> list[dict[str, str]]:
    """Python mirror of kavach/static/floor.js messagesFromStep."""
    title = re.sub(r"^\d+[a-z]?\. ", "", title or "")
    msgs: list[dict[str, str]] = []
    buyer = BUYER_QUOTE.search(detail)
    seller = SELLER_QUOTE.search(detail)
    decision = DECISION.search(detail)
    if buyer:
        msgs.append({"who": "buyer", "text": buyer.group(1), "kind": "say"})
    if seller:
        msgs.append({"who": "seller", "text": seller.group(1), "kind": "say"})
    if decision:
        msgs.append(
            {
                "who": "buyer",
                "text": f"decision ({decision.group(1)}): {decision.group(2).strip()}",
                "kind": "aside",
            }
        )
    if not buyer:
        accept = re.search(r"Buyer accepts [^\n.]+", detail)
        if accept:
            msgs.insert(0, {"who": "buyer", "text": accept.group(0), "kind": "aside"})
    if not msgs:
        who = "kernel" if phase in {"checkout", "refuse", "done"} else "narrator"
        text = f"{title} — {detail}" if detail else title
        msgs.append({"who": who, "text": text, "kind": "beat"})
    return msgs


@pytest.mark.parametrize("seller_id", SELLERS)
@pytest.mark.parametrize("guardrails", [True, False], ids=["on", "off"])
def test_negotiated_runs_emit_parseable_quotes(seller_id: str, guardrails: bool):
    db, result = run_scenario(seller_id=seller_id, guardrails=guardrails, goal=AUDIO_GOAL)
    try:
        selected = any(step.phase == "discovery" and "Product selected" in step.title for step in result.story)
        if not selected:
            assert quote_count(result) == 0
            return
        assert quote_count(result) >= 2
        parsed = []
        for step in result.story:
            parsed.extend(messages_from_step(step.title, step.detail, step.phase))
        speakers = {msg["who"] for msg in parsed if msg["kind"] == "say"}
        assert "buyer" in speakers
        assert "seller" in speakers
        for msg in parsed:
            assert msg["text"].strip()
            assert msg["who"] in {"buyer", "seller", "kernel", "narrator"}
    finally:
        db.close()


def test_floor_js_still_parses_buyer_seller_quotes():
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "kavach" / "static" / "floor.js"
    text = source.read_text()
    assert 'Buyer: "([\\s\\S]*?)"' in text
    assert 'Seller: "([\\s\\S]*?)"' in text
    assert "function messagesFromStep" in text
    db, result = run_scenario(seller_id="seller_04", guardrails=True)
    try:
        titles = [step.title for step in result.story]
        assert any("switches the price" in title for title in titles)
        assert result.story[-1].phase == "refuse"
        kernel_msgs = [
            msg
            for step in result.story
            for msg in messages_from_step(step.title, step.detail, step.phase)
            if msg["who"] == "kernel"
        ]
        assert kernel_msgs
        assert any("GR-9" in msg["text"] or "bait-and-switch" in msg["text"] for msg in kernel_msgs)
    finally:
        db.close()
