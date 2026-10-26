"""Pressure tactics and AI-directed instructions in the email's words (US-04, US-09).

Rule-based, English and Hebrew, so social engineering and prompt injection are caught
even when the LLM is down or fooled (ADR-005, ADR-019). Subject, plain body and all
HTML text are checked, hidden text included: hidden instructions aimed at an AI are
the point of hiding them.

Matching runs on normalized text: zero-width and other format characters removed
(`pass​word`), Hebrew vowel marks removed, case folded, whitespace collapsed.
Hebrew has no word boundaries in the regex sense once prefixes attach (`והסיסמה`),
so Hebrew phrases match anywhere; English ones match whole words.
"""

import re
import unicodedata

from bs4 import BeautifulSoup, Tag

from app.models import AnalyzeRequest, Manipulation
from app.signals.base import Finding
from app.signals.hidden import is_hidden


def _en(*phrases: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(phrases) + r")\b")


def _he(*phrases: str) -> re.Pattern[str]:
    return re.compile("|".join(phrases))


PHRASES: dict[Manipulation, tuple[re.Pattern[str], ...]] = {
    "urgency": (
        _en(r"within \d+ (?:hours?|hrs?|minutes?|mins?|days?)", r"immediately", r"urgent(?:ly)?",
            r"act now", r"as soon as possible", r"final (?:notice|warning|reminder)",
            r"last chance", r"expires? (?:today|tonight|soon)",
            r"(?:account|access|mailbox) (?:will be|has been|is) (?:closed|suspended|locked|"
            r"deleted|terminated|disabled|deactivated|restricted|limited)",
            r"unusual (?:sign-?in|login|activity)", r"suspicious activity"),
        _he(r"דחו(?:ף|פה|פים|פות)", r"מיידי", r"תוך \d+ (?:שעות|דקות|ימים)", r"תוך (?:שעה|יום)",
            r"הודעה אחרונה",
            r"(?:חשבון|תיבת הדואר)\S* (?:שלך )?(?:ייחסם|יינעל|ייסגר|יושעה|נחסם|ננעל|נסגר|הושעה|"
            r"יבוטל|הוגבל)",
            r"פעילות חשודה", r"פעילות חריגה"),
    ),
    "authority": (
        _en(r"ceo", r"chief executive", r"it department", r"it support", r"help ?desk",
            r"security team", r"legal action", r"law enforcement", r"police", r"tax authority",
            r"irs", r"court order"),
        _he(r'מנכ"ל', r"מחלקת (?:ה)?מחשוב", r"מחלקת it", r"צוות (?:ה)?אבטחה", r"רשות המסים",
            r"משטרה", r"משטרת ישראל", r"תביעה משפטית", r"הליכים משפטיים", r"צו בית משפט"),
    ),
    "credentials": (
        _en(r"password", r"passcode", r"verification code", r"one-?time (?:code|password)",
            r"otp", r"login (?:details|credentials)", r"credentials",
            r"(?:verify|confirm|validate|update) your (?:account|identity|details|password|"
            r"login|information)",
            r"social security number"),
        _he(r"סיסמ[הא]", r"קוד (?:ה)?אימות", r"קוד חד[- ]?פעמי", r"פרטי (?:ה)?התחברות",
            r"(?:אמת|אשר|עדכן) את (?:ה)?(?:חשבון|זהות|פרטי)", r"אימות (?:ה)?(?:חשבון|זהות)"),
    ),
    "financial": (
        _en(r"wire transfer", r"bank transfer", r"gift ?cards?", r"bitcoin", r"crypto ?wallet",
            r"payment (?:is )?overdue", r"overdue (?:invoice|payment)",
            r"outstanding (?:invoice|payment|balance)",
            r"update (?:your )?(?:payment|billing|bank) (?:details|information|method)",
            r"credit card (?:number|details)", r"new bank (?:account|details)",
            r"change (?:of|in) bank (?:account|details)"),
        _he(r"העברה בנקאית", r"העברת כספים", r"כרטיס(?:י)? מתנה", r"ביטקוין", r"תשלום (?:ב)?פיגור",
            r"חוב פתוח", r"(?:עדכן|עדכנו) (?:את )?פרטי (?:ה)?(?:תשלום|אשראי)",
            r"פרטי (?:כרטיס )?(?:ה)?אשראי", r"חשבון בנק חדש"),
    ),
}  # fmt: skip

AI_INSTRUCTIONS = (
    _en(r"(?:ignore|disregard|forget) (?:all |any )?(?:the )?(?:previous|prior|above|earlier) "
        r"(?:instructions|prompts?|rules)",
        r"(?:classify|mark|treat|rate|label|flag) (?:this|the) (?:email|message|mail) as "
        r"(?:safe|legitimate|benign|clean|trusted|not (?:spam|phishing|malicious))",
        r"(?:set|give|assign|return) (?:it |this (?:email|message) )?(?:a |the )?(?:risk )?"
        r"score (?:of |to |= ?)?0\b",
        r"(?:you are|as) an? (?:ai|language model|llm|assistant)",
        r"(?:ai|llm) (?:assistant|model|scanner|filter)s?:",
        r"system prompt", r"new instructions:"),
    _he(r"התעלם (?:מכל )?(?:ה)?הוראות",
        r"(?:סווג|סמן) (?:את )?(?:המייל|ההודעה|הדואר)\S* (?:הזה |הזו )?כ(?:בטוח|לגיטימי)",
        r"אתה מודל שפה", r"הוראות חדשות:"),
)  # fmt: skip

PRESSURE: set[Manipulation] = {"urgency", "authority"}
REQUEST: set[Manipulation] = {"credentials", "financial"}

_HEBREW_QUOTES = str.maketrans({"״": '"', "”": '"', "“": '"', "'": '"', "׳": '"', "’": '"'})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # Format characters (zero-width, bidi) and combining marks (Hebrew vowels, accents).
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text)
                   if unicodedata.category(ch) not in ("Cf", "Mn"))  # fmt: skip
    return re.sub(r"\s+", " ", text.translate(_HEBREW_QUOTES).casefold()).strip()


def email_text(request: AnalyzeRequest) -> str:
    """Subject, plain body and all HTML text (hidden included), normalized."""
    parts = [request.subject, request.body_text]
    if request.body_html:
        soup = BeautifulSoup(request.body_html, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()
        parts.append(soup.get_text(" "))
    return normalize(" ".join(parts))


def hidden_text(request: AnalyzeRequest) -> str:
    """Text hidden from the reader with inline styles (same rules as `hidden.py`), normalized."""
    if not request.body_html:
        return ""
    soup = BeautifulSoup(request.body_html, "html.parser")
    parts = [element.get_text(" ") for element in soup.find_all(style=True)
             if isinstance(element, Tag) and is_hidden(str(element["style"]))]  # fmt: skip
    return normalize(" ".join(parts))


def _has_ai_instructions(text: str) -> bool:
    return any(pattern.search(text) for pattern in AI_INSTRUCTIONS)


def tactics(text: str) -> list[Manipulation]:
    """Pressure tactics found, in a fixed order."""
    return [label for label, patterns in PHRASES.items()
            if any(pattern.search(text) for pattern in patterns)]  # fmt: skip


def labels(request: AnalyzeRequest) -> list[Manipulation]:
    """Tactics for the response's `manipulation` list; empty if the check can't run."""
    try:
        return tactics(email_text(request))
    except Exception:  # noqa: BLE001 - the engine already reports a failed language check
        return []


def check(request: AnalyzeRequest) -> list[Finding]:
    text = email_text(request)
    findings = []
    found = tactics(text)
    if found:
        # Pressure plus a request for credentials or money is the phishing formula;
        # either alone is common in legitimate mail (one-time codes, invoices).
        strong = PRESSURE.intersection(found) and REQUEST.intersection(found)
        finding_id = "manipulation_strong" if strong else "manipulation"
        findings.append(Finding(finding_id, tuple(found)))
    # Hidden from the reader and addressed to a scanner: no legitimate email does this.
    # Visible phrasing can be legitimate (a newsletter about AI attacks), so it scores less.
    if _has_ai_instructions(hidden_text(request)):
        findings.append(Finding("ai_instructions_hidden"))
    elif _has_ai_instructions(text):
        findings.append(Finding("ai_instructions"))
    return findings
