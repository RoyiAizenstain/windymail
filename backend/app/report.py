"""Manual report to the SOC webhook (ADR-008, US-06).

The report carries identifiers and the score only: the Gmail message ID, the score
and verdict, the reason IDs, and the reporter's salted hash. Never the subject, the
sender or the body. The webhook URL comes from the environment only, so nothing in
an email can steer where a report goes (no SSRF).

The score is the add-on's copy of what /analyze returned, so a user can misstate
it; a report is the user's own claim, and the SOC triages it as such.
"""

import logging
import time
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import ReportRequest
from app.verdict import verdict_for

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5.0


def send_report(report: ReportRequest, user_hash: str) -> None:
    """Posts the report to the SOC webhook; 404 in personal mode, 502 if not delivered."""
    url = get_settings().soc_webhook_url
    if url is None:
        # Personal mode has no security team to report to (ADR-015).
        raise HTTPException(status_code=404, detail="Not Found")

    payload = {
        "event": "user_report",
        "source": "windymail",
        "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reporter": user_hash,
        "message_id": report.message_id,
        "score": report.score,
        "verdict": verdict_for(report.score),
        "reason_ids": report.reason_ids,
    }

    started = time.monotonic()
    outcome = "ok"
    try:
        response = httpx.post(
            url, json=payload, timeout=WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False
        )
        if not response.is_success:
            outcome = f"status:{response.status_code}"
    except httpx.TimeoutException:
        outcome = "timeout"
    except httpx.HTTPError as err:
        outcome = f"error:{type(err).__name__}"
    finally:
        # Outcome and latency only: never the URL (it is a secret) or the payload.
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info("report: outcome=%s user=%s latency_ms=%d", outcome, user_hash, latency_ms)

    if outcome != "ok":
        raise HTTPException(status_code=502, detail="Report could not be delivered")
