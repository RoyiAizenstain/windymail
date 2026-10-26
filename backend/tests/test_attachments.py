import pytest

from app.models import AnalyzeRequest
from app.signals.attachments import assess, check


@pytest.mark.parametrize(
    ("filename", "finding_id", "values"),
    [
        ("setup.exe", "attachment_executable", (".exe",)),
        ("Invoice.JS", "attachment_executable", (".js",)),
        ("run.ps1", "attachment_executable", (".ps1",)),
        ("shortcut.lnk", "attachment_executable", (".lnk",)),
        ("invoice.exe.", "attachment_executable", (".exe",)),  # Windows drops the dot
        ("invoice.exe   ", "attachment_executable", (".exe",)),
        ("invoice.pdf.exe", "attachment_double_extension", (".pdf.exe",)),
        ("scan.jpg  .scr", "attachment_double_extension", (".jpg.scr",)),
        ("invoice‮gpj.exe", "attachment_disguised_name", ()),  # shows as invoiceexe.jpg
        ("report.docm", "attachment_macro", (".docm",)),
        ("budget.xlsm", "attachment_macro", (".xlsm",)),
        ("delivery.iso", "attachment_disk_image", (".iso",)),
        ("statement.html", "attachment_web_page", (".html",)),
        ("logo.svg", "attachment_web_page", (".svg",)),
        ("files.zip", "attachment_archive", (".zip",)),
    ],
)
def test_risky_attachments(filename: str, finding_id: str, values: tuple) -> None:
    finding = assess(filename)
    assert finding is not None
    assert (finding.id, finding.values) == (finding_id, values)


@pytest.mark.parametrize(
    "filename",
    ["report.pdf", "photo.jpg", "notes.docx", "data.csv", "README", "", "archive.tar.gz.pdf"],
)
def test_ordinary_attachments(filename: str) -> None:
    assert assess(filename) is None


def test_filename_never_echoed() -> None:
    finding = assess("Salary-Cohen-2026.pdf.exe")
    assert finding is not None
    assert all("cohen" not in v.lower() for v in finding.values)


def test_check_reports_each_risky_attachment() -> None:
    request = AnalyzeRequest.model_validate(
        {
            "message_id": "m",
            "from": "a@example.com",
            "subject": "",
            "body_text": "",
            "attachments": [
                {"filename": n, "mime_type": "application/octet-stream", "size_bytes": 1}
                for n in ("a.exe", "b.pdf", "c.zip")
            ],
        }
    )
    assert [f.id for f in check(request)] == ["attachment_executable", "attachment_archive"]
