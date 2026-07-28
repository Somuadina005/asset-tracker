"""
chatbot.py
Optional AI assistant for the Asset Tracker web app.

This is intentionally kept separate from notification_service.py --
the notification worker stays 100% rule-based with zero AI dependency.
This module is only imported by app.py (the web UI) so the operator
can ask natural-language questions like "what's low on stock?" or
"who has the drill checked out?" instead of clicking through pages.

Requires an ANTHROPIC_API_KEY environment variable. If it isn't set,
the chatbot route degrades gracefully with a clear message instead of
crashing the whole app.
"""

import os

from anthropic import Anthropic

from tracker import AssetTracker

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an inventory assistant embedded in an internal \
Asset Tracking System. You are given a live snapshot of the asset database \
(assets, quantities, thresholds, who has what checked out). Answer the \
operator's question using ONLY that snapshot. Be concise -- a few sentences \
or a short list, not an essay. If the answer isn't in the snapshot, say so \
plainly instead of guessing."""


def _build_snapshot(tracker: AssetTracker) -> str:
    assets = tracker.list_all_assets()
    lines = []
    for a in assets:
        holder = f", held by {a.current_holder}" if a.current_holder else ""
        low = " [LOW STOCK]" if a.is_low_stock() else ""
        lines.append(
            f"- {a.asset_id}: {a.name} ({a.category}) | qty {a.quantity} "
            f"(threshold {a.low_stock_threshold}) | {a.status}{holder}{low}"
        )
    return "\n".join(lines) if lines else "(no assets in the system yet)"


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask(tracker: AssetTracker, question: str) -> str:
    """Answer a natural-language question about current inventory state."""
    if not is_configured():
        return (
            "The AI assistant isn't configured yet -- set the "
            "ANTHROPIC_API_KEY environment variable to enable it."
        )

    client = Anthropic()
    snapshot = _build_snapshot(tracker)

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Current inventory snapshot:\n{snapshot}\n\nQuestion: {question}",
            }
        ],
    )
    return "".join(block.text for block in response.content if block.type == "text")
