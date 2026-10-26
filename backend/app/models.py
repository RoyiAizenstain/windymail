"""API request and response schemas (docs/architecture.md, Section 3).

Every request field is untrusted input: unknown fields are rejected and every
string and list has an upper bound.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import Mode

Verdict = Literal["safe", "suspicious", "malicious"]
Category = Literal["sender", "link", "attachment", "content", "manipulation"]
Severity = Literal["low", "medium", "high"]
Manipulation = Literal["urgency", "authority", "credentials", "financial"]


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


class Reason(StrictModel):
    id: str
    category: Category
    severity: Severity
    text: str
    details: str


class Herd(StrictModel):
    count: int = Field(ge=0)
    window_minutes: int = Field(gt=0)


class AnalyzeResponse(StrictModel):
    score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary: str
    reasons: list[Reason]
    manipulation: list[Manipulation]
    herd: Herd | None = None
    partial: bool = False
    mode: Mode


class HealthResponse(StrictModel):
    status: Literal["ok"]
