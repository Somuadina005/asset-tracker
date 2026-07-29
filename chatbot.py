"""
chatbot.py
AI Asset Copilot entry point used by the web UI (app.py's /chatbot route).

This module used to contain the Anthropic API call directly. The AI logic
has since moved into ai_service.AIService (a clean service layer, per the
project's layered-architecture convention: Flask routes -> business/service
logic -> data). This file is kept so app.py's existing
`import chatbot` / `chatbot.ask(tracker, question)` / `chatbot.is_configured()`
calls keep working completely unchanged.

This is intentionally kept separate from notification_service.py --
the notification worker stays 100% rule-based with zero AI dependency.

Requires an ANTHROPIC_API_KEY environment variable. If it isn't set,
is_configured() returns False and ask() degrades gracefully with a clear
message instead of crashing the whole app.
"""

from tracker import AssetTracker
from ai_service import AIService

_service = AIService()


def is_configured() -> bool:
    return _service.is_configured()


def ask(tracker: AssetTracker, question: str) -> str:
    """Answer a natural-language question about current inventory state,
    asset health, departments, warranties, etc."""
    return _service.ask(tracker, question)
