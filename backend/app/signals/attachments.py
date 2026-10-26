"""Attachments whose type is risky to open (US-03). Names and types only: attachment
contents never leave Gmail (ADR-013, threat model "Out of Scope").

Only the extension is reported, never the filename (ADR-017).
"""

from app.models import AnalyzeRequest
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


def check(request: AnalyzeRequest) -> list[Finding]:
    findings = []
    for attachment in request.attachments:
        finding = assess(attachment.filename)
        if finding:
            findings.append(finding)
    return findings


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
