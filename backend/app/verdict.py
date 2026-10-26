"""Score to verdict mapping. Thresholds per CLAUDE.md and ADR-014."""

from app.models import Verdict

SUSPICIOUS_MIN = 30
MALICIOUS_MIN = 70


def verdict_for(score: int) -> Verdict:
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    if score >= MALICIOUS_MIN:
        return "malicious"
    if score >= SUSPICIOUS_MIN:
        return "suspicious"
    return "safe"
