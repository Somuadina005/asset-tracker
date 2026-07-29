"""
ai_service.py
Service layer for the AI Asset Copilot.

This is where the "AI Asset Copilot" feature actually lives. chatbot.py
stays as a thin adapter (kept for backward compatibility with app.py's
existing `import chatbot` / `chatbot.ask(...)` / `chatbot.is_configured()`
calls) that just delegates here -- this file is the AIService the spec
asks for: Flask routes never touch the Anthropic SDK directly, and this
module never touches Flask.

Why a "context" instead of the raw database
--------------------------------------------
Rather than dumping every column of every table (assets + logs +
notification_log) at the model, build_context() reuses the same
business-logic layer (AssetTracker) the rest of the app uses to compute a
compact, analysis-ready summary: totals, low-stock items, health-score
distribution (from health_score_service.py), warranty status, department
breakdown, and checkout activity. This keeps the prompt small, keeps the
model from having to re-derive arithmetic it could get wrong, and avoids
ever sending raw holder/personnel log rows the operator didn't ask about.
"""

import os
from collections import Counter
from datetime import date, datetime

from anthropic import Anthropic

from tracker import AssetTracker
from health_score_service import parse_date  # shared date parsing helper

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are the AI Asset Copilot embedded in an internal \
Asset Tracking System. You are given a computed snapshot of the asset \
database -- summary statistics plus a per-asset listing (health score, \
department, stock levels, warranty status). Answer the operator's \
question using ONLY that snapshot.

Do not just repeat rows back verbatim. Analyze the data: total up what's \
being asked for, call out what needs attention, and give a short, concrete \
recommendation when relevant (e.g. what to replace, what to purchase, \
what to check on). Keep answers concise -- a few sentences or a short \
list, similar to how a knowledgeable operations manager would summarize \
things out loud. If the snapshot doesn't contain what's needed to answer, \
say so plainly instead of guessing."""


class AIService:
    """Thin wrapper around the Anthropic API for asset Q&A. Holds no
    business logic of its own -- all data comes from AssetTracker."""

    def __init__(self, model: str = MODEL):
        self.model = model
        self._client = None  # created lazily so import-time never requires the key

    def is_configured(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic()
        return self._client

    # ---------- Context building ----------

    def _department_breakdown(self, assets):
        counts = Counter(a.department for a in assets if a.department)
        if not counts:
            return "  (no department data recorded on any asset yet)"
        lines = [f"  {dept}: {count} asset(s)" for dept, count in counts.most_common()]
        return "\n".join(lines)

    def _summary_stats(self, assets, low_stock, checkout_counts):
        checked_out = [a for a in assets if a.status == "Checked Out"]
        scored = [a for a in assets if a.health_score is not None]
        replace_soon = [a for a in scored if a.health_status == "Replace Soon"]
        monitor = [a for a in scored if a.health_status == "Monitor"]
        expired_warranty = [
            a for a in assets
            if parse_date(a.warranty_expiration) and parse_date(a.warranty_expiration) < date.today()
        ]

        lines = [
            f"Total assets: {len(assets)}",
            f"Available: {len(assets) - len(checked_out)}",
            f"Checked out: {len(checked_out)}",
            f"Low stock: {len(low_stock)}",
        ]
        if scored:
            lines.append(
                f"Health scores computed for {len(scored)}/{len(assets)} assets -- "
                f"{len(replace_soon)} flagged Replace Soon, {len(monitor)} flagged Monitor."
            )
        else:
            lines.append("Health scores have not been calculated yet.")
        if expired_warranty:
            lines.append(f"Assets with an expired warranty: {len(expired_warranty)}")
        if checkout_counts:
            top_id, top_count = max(checkout_counts.items(), key=lambda kv: kv[1])
            top_asset = next((a for a in assets if a.asset_id == top_id), None)
            if top_asset:
                lines.append(
                    f"Most checked-out asset: {top_asset.name} ({top_id}), "
                    f"{top_count} lifetime checkout(s)."
                )
        return "\n".join(lines)

    def _asset_lines(self, assets, checkout_counts):
        lines = []
        for a in assets:
            bits = [f"{a.asset_id}: {a.name} ({a.category or 'uncategorized'})"]
            if a.department:
                bits.append(f"dept={a.department}")
            bits.append(f"qty={a.quantity}")
            if a.is_low_stock():
                bits.append("LOW STOCK")
            bits.append(a.status)
            if a.current_holder:
                bits.append(f"held by {a.current_holder}")
            checkouts = checkout_counts.get(a.asset_id, 0)
            if checkouts:
                bits.append(f"{checkouts} checkout(s)")
            if a.health_score is not None:
                bits.append(f"health={a.health_score} ({a.health_status})")
            warranty_date = parse_date(a.warranty_expiration)
            if warranty_date:
                flag = " EXPIRED" if warranty_date < date.today() else ""
                bits.append(f"warranty {a.warranty_expiration}{flag}")
            lines.append("- " + " | ".join(bits))
        return "\n".join(lines) if lines else "(no assets in the system yet)"

    def build_context(self, tracker: AssetTracker) -> str:
        """Compute a compact, analysis-ready snapshot of the current
        inventory state -- the 'necessary context' sent to the LLM instead
        of the raw database."""
        assets = tracker.list_all_assets()
        low_stock = tracker.get_low_stock_alerts()
        checkout_counts = tracker.get_checkout_counts()

        return (
            "=== Summary ===\n"
            f"{self._summary_stats(assets, low_stock, checkout_counts)}\n\n"
            "=== Assets by department ===\n"
            f"{self._department_breakdown(assets)}\n\n"
            "=== Per-asset detail ===\n"
            f"{self._asset_lines(assets, checkout_counts)}"
        )

    # ---------- Public entry point ----------

    def ask(self, tracker: AssetTracker, question: str) -> str:
        if not self.is_configured():
            return (
                "The AI assistant isn't configured yet -- set the "
                "ANTHROPIC_API_KEY environment variable to enable it."
            )

        client = self._get_client()
        context = self.build_context(tracker)

        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Current inventory snapshot:\n{context}\n\nQuestion: {question}",
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")
