"""API request and response schemas (docs/architecture.md, Section 3).

Every request field is untrusted input: unknown fields are rejected and every
string and list has an upper bound.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Mode

Verdict = Literal["safe", "suspicious", "malicious"]
Category = Literal["sender", "link", "attachment", "content", "manipulation"]
Severity = Literal["low", "medium", "high"]
Manipulation = Literal["urgency", "authority", "credentials", "financial", "impersonation"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attachment(StrictModel):
    filename: str = Field(max_length=512)
    mime_type: str = Field(max_length=255)
    size_bytes: int = Field(ge=0)


class AnalyzeRequest(StrictModel):
    message_id: str = Field(min_length=1, max_length=256)
    sender: str = Field(alias="from", max_length=1_000)
    reply_to: str | None = Field(default=None, max_length=1_000)
    subject: str = Field(max_length=2_000)
    auth_results: str | None = Field(default=None, max_length=10_000)
    body_text: str = Field(max_length=100_000)
    body_html: str | None = Field(default=None, max_length=150_000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=50)
    # Set by the add-on when a body was cut to fit the size limits.
    truncated: bool = False


class Reason(StrictModel):
    id: str
    category: Category
    severity: Severity
    text: str
    details: str
    # Which check found it, so the card can say the AI check helped (ADR-019).
    source: Literal["rules", "ai"] = "rules"
    # What this reason added to the score (ADR-010), shown in Technical details.
    points: int = Field(default=0, ge=0, le=100)


class AiCheck(StrictModel):
    """What the AI check found, as labels only; the card words them (ADR-019)."""

    ran: bool
    tactics: list[Manipulation] = Field(default_factory=list)
    injection: bool = False


class Herd(StrictModel):
    count: int = Field(ge=0)
    window_minutes: int = Field(gt=0)


class AnalyzeResponse(StrictModel):
    score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary: str
    reasons: list[Reason]
    manipulation: list[Manipulation]
    ai: AiCheck = Field(default_factory=lambda: AiCheck(ran=False))
    herd: Herd | None = None
    partial: bool = False
    mode: Mode


class ReportRequest(StrictModel):
    """A user's manual report (ADR-008): identifiers and the score only, never content."""

    message_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
    score: int = Field(ge=0, le=100, strict=True)
    reason_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("reason_ids")
    @classmethod
    def known_reason_ids(cls, ids: list[str]) -> list[str]:
        # Only IDs this backend can produce reach the SOC; anything else is a 422.
        from app.signals.messages import CATALOG  # messages imports this module

        if any(reason_id not in CATALOG for reason_id in ids):
            raise ValueError("unknown reason id")
        return list(dict.fromkeys(ids))


class ReportResponse(StrictModel):
    status: Literal["received"]


class HealthResponse(StrictModel):
    status: Literal["ok"]
