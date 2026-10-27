"""The score (ADR-010): points per reason by severity, added up, clamped to 0-100.

Points are per reason, not per occurrence: ten shortened links count once, so volume
alone cannot push an email to Malicious. Each reason carries its points, so the card
can show how the score was reached.

LLM reasons add at most LLM_CAP points and never subtract (ADR-003, ADR-019): a fooled
model can fail to add points, but cannot make a malicious email look safer.

A few decisive findings set a minimum of DECISIVE_FLOOR on their own, because no
legitimate email does them.
"""

from dataclasses import dataclass

from app.models import Reason

SEVERITY_POINTS = {"high": 35, "medium": 15, "low": 5}
LLM_CAP = 20
DECISIVE_FLOOR = 70

# Each entry needs a reason: why no legitimate email would ever show it.
DECISIVE = {
    # A trusted extension in front of a program exists only to disguise the program.
    "attachment_double_extension",
    # Reversing how a file name displays exists only to hide its real extension.
    "attachment_disguised_name",
    # Hiding a message for a scanner from the reader exists only to fool the scanner.
    "ai_instructions_hidden",
    # A program, web page or archive named as a trusted document exists only to disguise it.
    "attachment_type_mismatch",
}


@dataclass(frozen=True)
class Scored:
    score: int
    reasons: list[Reason]  # each with its points; rules first, then the LLM's
    floored: bool  # a decisive finding lifted the score to DECISIVE_FLOOR


def score(rule_reasons: list[Reason], llm_reasons: list[Reason]) -> Scored:
    reasons = [r.model_copy(update={"points": SEVERITY_POINTS[r.severity]}) for r in rule_reasons]
    budget = LLM_CAP
    for reason in llm_reasons:
        points = min(budget, SEVERITY_POINTS[reason.severity])
        budget -= points
        reasons.append(reason.model_copy(update={"points": points}))

    total = min(100, sum(reason.points for reason in reasons))
    floored = total < DECISIVE_FLOOR and any(r.id in DECISIVE for r in rule_reasons)
    return Scored(max(total, DECISIVE_FLOOR) if floored else total, reasons, floored)
