"""Every reason's wording, in one place (US-02).

`text` is shown to the user and is fixed wording; `text_many` is used when the same
finding occurs more than once. `details` labels the analyst view (US-10). Nothing
here is built from email content (ADR-017).
"""

from dataclasses import dataclass

from app.models import Category, Severity


@dataclass(frozen=True)
class Message:
    category: Category
    severity: Severity
    text: str
    text_many: str
    details: str


CATALOG: dict[str, Message] = {
    "body_truncated": Message(
        category="content",
        severity="low",
        text="This email is too long to check fully. Parts of it were not checked.",
        text_many="This email is too long to check fully. Parts of it were not checked.",
        details="Body cut to fit the size limit before analysis",
    ),
    "check_failed": Message(
        category="content",
        severity="low",
        text="One of the checks couldn't run on this email.",
        text_many="{count} of the checks couldn't run on this email.",
        details="Checks that failed",
    ),
}
