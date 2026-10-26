"""Provisional score until ADR-010 closes: points per reason by severity, clamped to 0-100.

Points are per reason, not per occurrence: ten shortened links count once, so volume
alone cannot push an email to Malicious.

LLM reasons add at most LLM_CAP points and never subtract (ADR-003, ADR-019): a fooled
model can fail to add points, but cannot make a malicious email look safer.
"""

from app.models import Reason

SEVERITY_POINTS = {"high": 35, "medium": 15, "low": 5}
LLM_CAP = 20


def provisional_score(reasons: list[Reason]) -> int:
    return min(100, sum(SEVERITY_POINTS[reason.severity] for reason in reasons))


def combined_score(deterministic: list[Reason], llm: list[Reason]) -> int:
    llm_points = min(LLM_CAP, sum(SEVERITY_POINTS[reason.severity] for reason in llm))
    return min(100, provisional_score(deterministic) + llm_points)
