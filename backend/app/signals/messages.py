"""Every reason's wording, in one place (US-02).

`text` is shown to the user and is fixed wording; `text_many`, when set, is used if
the same finding occurs more than once. `details` labels the analyst view (US-10).
Nothing here is built from email content (ADR-017).
"""

from dataclasses import dataclass

from app.models import Category, Severity


@dataclass(frozen=True)
class Message:
    category: Category
    severity: Severity
    text: str
    details: str
    text_many: str | None = None


CATALOG: dict[str, Message] = {
    # Sender
    "auth_unknown": Message(
        category="sender",
        severity="low",
        text="WindyMail couldn't confirm who really sent this email.",
        details="No sender authentication result from Gmail (mx.google.com)",
    ),
    "dmarc_fail": Message(
        category="sender",
        severity="high",
        text="This email failed the check that confirms it comes from the address it shows.",
        details="Authentication-Results",
    ),
    "spf_fail": Message(
        category="sender",
        severity="medium",
        text="This email was sent from a server the sender's domain doesn't list as its own.",
        details="Authentication-Results",
    ),
    "dkim_fail": Message(
        category="sender",
        severity="medium",
        text="This email's digital signature is invalid, so it may have been changed or forged.",
        details="Authentication-Results",
    ),
    "display_name_mismatch": Message(
        category="sender",
        severity="medium",
        text="The sender's name shows a different address than the one it really came from.",
        details="Domain in the display name, then the real sending domain",
    ),
    "display_name_brand": Message(
        category="sender",
        severity="medium",
        text="The sender's name uses a well-known company's name, "
        "but the email didn't come from that company.",
        text_many="The sender's name uses {count} well-known company names, "
        "but the email didn't come from them.",
        details="Brand named, then the real sending domain",
    ),
    "reply_to_mismatch": Message(
        category="sender",
        severity="medium",
        text="If you reply, your answer goes to a different domain than the sender's.",
        details="Sending domain, then the reply-to domain",
    ),
    # Content
    "body_truncated": Message(
        category="content",
        severity="low",
        text="This email is too long to check fully. Parts of it were not checked.",
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
