"""Checks about the message as a whole."""

from app.models import AnalyzeRequest
from app.signals.base import Finding


def check(request: AnalyzeRequest) -> list[Finding]:
    # Truncation is an evasion path (padding pushes a link past the cut), so it is a
    # finding rather than a silent gap.
    return [Finding("body_truncated")] if request.truncated else []
