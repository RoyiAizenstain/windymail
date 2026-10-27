"""Attachment inspection (ADR-021): findings from the facts the add-on read inside a file."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.models import AnalyzeRequest, Attachment, Inspection
from app.signals.attachments import assess_inspection, check

ANALYZE = "/api/v1/analyze"


def attachment(filename: str, **facts: object) -> Attachment:
    return Attachment(
        filename=filename,
        mime_type="application/octet-stream",
        size_bytes=1000,
        inspection=Inspection(inspected=True, **facts),
    )


def ids(att: Attachment) -> list[str]:
    return [f.id for f in assess_inspection(att)]


@pytest.mark.parametrize(
    ("filename", "kind"),
    [
        ("invoice.pdf", "exe"),
        ("photo.jpg", "exe"),
        ("statement.pdf", "html"),
        ("report.docx", "html"),
        ("invoice.pdf", "zip"),
        ("old.doc", "zip"),
    ],
)
def test_disguised_real_type(filename: str, kind: str) -> None:
    findings = assess_inspection(attachment(filename, kind=kind))
    assert findings[0].id == "attachment_type_mismatch"
    assert findings[0].values == (f".{filename.rsplit('.', 1)[1]}", f"real:{kind}")


@pytest.mark.parametrize(
    ("filename", "kind"),
    [
        ("report.pdf", "pdf"),
        ("notes.docx", "zip"),  # Office files are zips inside
        ("budget.xlsx", "zip"),
        ("old.doc", "ole"),
        ("page.txt", "html"),  # a text file may quote HTML
        ("setup.exe", "exe"),  # honest name: the extension rule covers it
        ("archive.zip", "zip"),
        ("photo.jpg", "unknown"),
        ("readme", "exe"),  # no trusted name to contradict; nothing to compare
    ],
)
def test_honest_real_type(filename: str, kind: str) -> None:
    assert "attachment_type_mismatch" not in ids(attachment(filename, kind=kind))


def test_encrypted_archive() -> None:
    assert ids(attachment("files.zip", kind="zip", encrypted=True)) == [
        "attachment_encrypted_archive"
    ]


def test_risky_file_inside_archive() -> None:
    entries = ["docs/", "docs/invoice.pdf.exe", "photo.jpg", "run.lnk", "notes.txt"]
    findings = assess_inspection(attachment("photos.zip", kind="zip", entries=entries))
    assert [f.id for f in findings] == ["attachment_archive_risky_file"]
    assert findings[0].values == (".pdf.exe", ".lnk")


def test_ordinary_archive_contents() -> None:
    entries = ["photos/a.jpg", "photos/b.png", "inner.zip", "notes.txt"]
    assert ids(attachment("photos.zip", kind="zip", entries=entries)) == []


def test_hidden_macros() -> None:
    findings = assess_inspection(attachment("report.docx", kind="zip", macros=True))
    assert [(f.id, f.values) for f in findings] == [("attachment_hidden_macros", (".docx",))]


def test_macros_in_a_macro_named_file_are_already_covered() -> None:
    assert ids(attachment("budget.xlsm", kind="zip", macros=True)) == []


def test_active_pdf() -> None:
    findings = assess_inspection(
        attachment("form.pdf", kind="pdf", pdf_actions=["javascript", "launch"])
    )
    assert [(f.id, f.values) for f in findings] == [
        ("attachment_pdf_active", ("javascript", "launch"))
    ]


def test_not_inspected_is_never_clean() -> None:
    att = Attachment(
        filename="big.pdf", mime_type="application/pdf", size_bytes=20_000_000,
        inspection=Inspection(inspected=False),
    )  # fmt: skip
    assert ids(att) == ["attachment_not_inspected"]


def test_no_inspection_field_keeps_old_behaviour() -> None:
    att = Attachment(filename="report.pdf", mime_type="application/pdf", size_bytes=1)
    assert ids(att) == []


def _request(*attachments: Attachment) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(
        {"message_id": "m", "from": "a@b.com", "subject": "s", "body_text": "",
         "attachments": [a.model_dump() for a in attachments]}
    )  # fmt: skip


def test_kill_switch_ignores_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    disguised = attachment("invoice.pdf", kind="exe")
    assert [f.id for f in check(_request(disguised))] == ["attachment_type_mismatch"]
    monkeypatch.setenv("ATTACHMENT_INSPECTION", "false")
    get_settings.cache_clear()
    assert check(_request(disguised)) == []


def test_disguised_program_alone_is_malicious(client: TestClient, valid_request: dict) -> None:
    valid_request["attachments"] = [
        {"filename": "invoice.pdf", "mime_type": "application/pdf", "size_bytes": 5000,
         "inspection": {"inspected": True, "kind": "exe"}}
    ]  # fmt: skip
    body = client.post(ANALYZE, json=valid_request).json()
    assert body["verdict"] == "malicious"
    assert any(r["id"] == "attachment_type_mismatch" for r in body["reasons"])


@pytest.mark.parametrize(
    "inspection",
    [
        {"inspected": True, "kind": "virus"},
        {"inspected": True, "pdf_actions": ["format_disk"]},
        {"inspected": True, "entries": ["a"] * 51},
        {"inspected": True, "entries": ["a" * 256]},
        {"inspected": True, "bytes": "TVqQ"},  # file content is never accepted
        {"kind": "exe"},  # inspected is required
        {"inspected": "yes"},
    ],
)
def test_invalid_inspection_is_422(
    client: TestClient, valid_request: dict, inspection: dict
) -> None:
    valid_request["attachments"][0]["inspection"] = inspection
    assert client.post(ANALYZE, json=valid_request).status_code == 422


def test_entry_names_are_not_echoed(client: TestClient, valid_request: dict) -> None:
    valid_request["attachments"][0]["inspection"] = {
        "inspected": True, "kind": "zip", "entries": ["SECRET-MARKER-91.exe"],
    }  # fmt: skip
    response = client.post(ANALYZE, json=valid_request)
    assert response.status_code == 200
    assert "SECRET-MARKER-91" not in response.text
