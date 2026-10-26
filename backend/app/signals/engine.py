"""Runs every check and turns findings into reasons.

Fail safe: a check that raises adds a "couldn't run" reason instead of failing the
request, so an email crafted to crash a check never looks cleaner than it is.
"""

import logging
import re
from collections.abc import Callable, Sequence

from app.models import AnalyzeRequest, Reason
from app.signals import content, links, lookalike, sender
from app.signals.base import Finding
from app.signals.messages import CATALOG

logger = logging.getLogger(__name__)

Check = Callable[[AnalyzeRequest], list[Finding]]

CHECKS: tuple[tuple[str, Check], ...] = (
    ("sender", sender.check),
    ("lookalike", lookalike.check),
    ("links", links.check),
    ("content", content.check),
)

# ADR-017: only lowercase domains, IPs, extensions and auth results reach the response.
_SAFE_VALUE = re.compile(r"[a-z0-9.:=_\-]{1,253}")
MAX_VALUES_PER_REASON = 10

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def run_checks(
    request: AnalyzeRequest, checks: Sequence[tuple[str, Check]] = CHECKS
) -> list[Reason]:
    findings: list[Finding] = []
    for name, check in checks:
        try:
            findings.extend(check(request))
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            # Error type only: exception messages can contain email content.
            logger.error("signals: check %s failed (%s)", name, type(exc).__name__)
            findings.append(Finding("check_failed", (name,)))
    return to_reasons(findings)


def to_reasons(findings: list[Finding]) -> list[Reason]:
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.id, []).append(finding)

    reasons = []
    for finding_id, group in grouped.items():
        message = CATALOG[finding_id]
        count = len(group)
        values = _safe_values(group)
        reasons.append(
            Reason(
                id=finding_id,
                category=message.category,
                severity=message.severity,
                text=message.text_many.format(count=count)
                if count > 1 and message.text_many
                else message.text,
                details=f"{message.details}: {', '.join(values)}" if values else message.details,
            )
        )
    return sorted(reasons, key=lambda reason: _SEVERITY_ORDER[reason.severity])


def _safe_values(group: list[Finding]) -> list[str]:
    values: list[str] = []
    for finding in group:
        for value in finding.values:
            if _SAFE_VALUE.fullmatch(value) and value not in values:
                values.append(value)
    return values[:MAX_VALUES_PER_REASON]


def summarize(reasons: list[Reason]) -> str:
    if not reasons:
        return "No warning signs found."
    if len(reasons) == 1:
        return "WindyMail found 1 warning sign."
    return f"WindyMail found {len(reasons)} warning signs."
