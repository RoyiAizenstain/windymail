"""Attachments whose type is risky to open (US-03).

Names and types, plus the structural facts the add-on read from each file (ADR-021):
its real type, a zip's table of contents, PDF actions. The file itself never leaves
Gmail. Only extensions and fixed labels are reported, never a filename (ADR-017).
"""

from app.config import get_settings
from app.models import AnalyzeRequest, Attachment
from app.signals.base import Finding

EXECUTABLE = {
    "exe", "scr", "com", "pif", "bat", "cmd", "js", "jse", "vbs", "vbe", "wsf", "wsh",
    "ps1", "hta", "msi", "lnk", "jar", "cpl", "reg", "scf",
}  # fmt: skip
MACRO = {"docm", "dotm", "xlsm", "xltm", "xlam", "pptm", "potm", "ppsm"}
DISK_IMAGE = {"iso", "img", "vhd", "vhdx"}
# HTML attachments open in the browser and can rebuild a file there (HTML smuggling).
WEB_PAGE = {"html", "htm", "shtml", "xhtml", "svg"}
ARCHIVE = {"zip", "rar", "7z", "gz", "tar", "ace", "cab", "arj"}
# Extensions people trust, used as a disguise in front of the real one.
DECOY = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "jpg", "jpeg", "png", "csv"}

# Characters that reorder how a name is displayed: `invoice‮gpj.exe` shows as
# `invoiceexe.jpg`.
BIDI_CONTROLS = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F)}

_BY_TYPE = (
    (EXECUTABLE, "attachment_executable"),
    (MACRO, "attachment_macro"),
    (DISK_IMAGE, "attachment_disk_image"),
    (WEB_PAGE, "attachment_web_page"),
    (ARCHIVE, "attachment_archive"),
)


# Office formats that are zip files inside; any other trusted name on a zip is a disguise.
OOXML = {"docx", "xlsx", "pptx", "docm", "xlsm", "pptm", "dotx", "dotm", "xltx", "xltm"}
# Names that never hide a program or a web page in normal use.
_NOT_A_PAGE = {"txt", "csv", "xml"}


def check(request: AnalyzeRequest) -> list[Finding]:
    inspect = get_settings().attachment_inspection
    findings = []
    for attachment in request.attachments:
        finding = assess(attachment.filename)
        if finding:
            findings.append(finding)
        if inspect and attachment.inspection is not None:
            findings += assess_inspection(attachment)
    return findings


def assess_inspection(attachment: Attachment) -> list[Finding]:
    """Findings from what the add-on saw inside the file (ADR-021)."""
    facts = attachment.inspection
    if facts is None:
        return []
    if not facts.inspected:
        # Never treated as clean: the user is told the inside wasn't checked.
        return [Finding("attachment_not_inspected")]
    findings = []
    extension = _extension(attachment.filename)
    if _disguised(extension, facts.kind):
        findings.append(
            Finding("attachment_type_mismatch", (f".{extension}", f"real:{facts.kind}"))
        )
    if facts.encrypted:
        findings.append(Finding("attachment_encrypted_archive"))
    inner = [assess(name.rsplit("/", 1)[-1]) for name in facts.entries]
    risky = [f for f in inner if f and f.id != "attachment_archive"]
    if risky:
        findings.append(
            Finding("attachment_archive_risky_file", tuple(v for f in risky for v in f.values))
        )
    if facts.macros and extension not in MACRO:
        findings.append(Finding("attachment_hidden_macros", (f".{extension}",)))
    if facts.pdf_actions:
        findings.append(Finding("attachment_pdf_active", tuple(facts.pdf_actions)))
    return findings


def _disguised(extension: str, kind: str | None) -> bool:
    """The real type contradicts a name people trust: no legitimate file does this."""
    if extension not in DECOY:
        return False
    if kind == "exe":
        return True
    if kind == "html":
        return extension not in _NOT_A_PAGE
    if kind == "zip":
        return extension not in OOXML
    return False


def _extension(filename: str) -> str:
    parts = filename.lower().rstrip(". ").rsplit(".", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def assess(filename: str) -> Finding | None:
    if any(ch in BIDI_CONTROLS for ch in filename):
        return Finding("attachment_disguised_name")
    # Windows drops trailing dots and spaces: `invoice.exe. ` runs as `invoice.exe`.
    parts = [part.strip() for part in filename.lower().rstrip(". ").split(".")]
    if len(parts) < 2:
        return None
    extension = parts[-1]
    if extension in EXECUTABLE and len(parts) >= 3 and parts[-2] in DECOY:
        return Finding("attachment_double_extension", (f".{parts[-2]}.{extension}",))
    for extensions, finding_id in _BY_TYPE:
        if extension in extensions:
            return Finding(finding_id, (f".{extension}",))
    return None
