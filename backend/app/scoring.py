"""Provisional score until ADR-010 closes: points per reason by severity, clamped to 0-100.

Points are per reason, not per occurrence: ten shortened links count once, so volume
alone cannot push an email to Malicious.
"""

from app.models import Reason

SEVERITY_POINTS = {"high": 35, "medium": 15, "low": 5}


def provisional_score(reasons: list[Reason]) -> int:
    return min(100, sum(SEVERITY_POINTS[reason.severity] for reason in reasons))
