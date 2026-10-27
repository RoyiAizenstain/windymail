import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import report
from app.config import get_settings
from app.main import create_app
from tests.conftest import AUTH_HEADERS

REPORT = "/api/v1/report"
WEBHOOK = "https://soc.example.com/hook-secret-path"


@pytest.fixture
def valid_report() -> dict:
    return {"message_id": "18f3a9c2b4d5e6f7", "score": 82, "reason_ids": ["dmarc_fail"]}


@pytest.fixture
def webhook(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Organization mode with a fake webhook that records each post."""
    monkeypatch.setenv("SOC_WEBHOOK_URL", WEBHOOK)
    get_settings.cache_clear()
    posts: list[dict] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        posts.append({"url": url, **kwargs})
        return httpx.Response(200)

    monkeypatch.setattr(report.httpx, "post", fake_post)
    return posts


@pytest.fixture
def org_client(webhook: list[dict]) -> TestClient:
    return TestClient(create_app(), headers=AUTH_HEADERS)


def failing_post(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(report.httpx, "post", fake_post)


def test_report_is_forwarded(org_client: TestClient, webhook: list, valid_report: dict) -> None:
    response = org_client.post(REPORT, json=valid_report)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}
    assert len(webhook) == 1
    post = webhook[0]
    assert post["url"] == WEBHOOK
    assert post["timeout"] == report.WEBHOOK_TIMEOUT_SECONDS
    assert post["follow_redirects"] is False


def test_payload_carries_identifiers_only(
    org_client: TestClient, webhook: list, valid_report: dict
) -> None:
    org_client.post(REPORT, json=valid_report)
    payload = webhook[0]["json"]
    assert set(payload) == {
        "event", "source", "reported_at", "reporter", "message_id", "score", "verdict",
        "reason_ids",
    }  # fmt: skip
    assert payload["message_id"] == "18f3a9c2b4d5e6f7"
    assert payload["score"] == 82
    assert payload["verdict"] == "malicious"  # derived here, not taken from the add-on
    assert payload["reason_ids"] == ["dmarc_fail"]
    assert payload["reporter"] != "user-123"  # hashed, never the raw Google ID


def test_duplicate_reason_ids_are_sent_once(
    org_client: TestClient, webhook: list, valid_report: dict
) -> None:
    valid_report["reason_ids"] = ["dmarc_fail", "dmarc_fail"]
    org_client.post(REPORT, json=valid_report)
    assert webhook[0]["json"]["reason_ids"] == ["dmarc_fail"]


def test_personal_mode_is_404(client: TestClient, valid_report: dict) -> None:
    assert client.post(REPORT, json=valid_report).status_code == 404


def test_requires_token(webhook: list, anon_client: TestClient, valid_report: dict) -> None:
    assert anon_client.post(REPORT, json=valid_report).status_code == 401
    assert webhook == []


@pytest.mark.parametrize(
    "change",
    [
        {"reason_ids": ["<script>"]},
        {"reason_ids": ["not_a_reason"]},
        {"reason_ids": ["dmarc_fail"] * 51},
        {"score": 101},
        {"score": -1},
        {"score": "82"},
        {"message_id": ""},
        {"message_id": "a" * 257},
        {"message_id": "../../etc"},
        {"subject": "extra field"},
        {"body_text": "no content in reports"},
    ],
)
def test_invalid_report_is_422_and_not_sent(
    org_client: TestClient, webhook: list, valid_report: dict, change: dict
) -> None:
    response = org_client.post(REPORT, json={**valid_report, **change})
    assert response.status_code == 422
    assert webhook == []


@pytest.mark.parametrize(
    "result",
    [
        httpx.Response(500),
        httpx.Response(302, headers={"Location": "https://elsewhere.example"}),
        httpx.ConnectTimeout("slow"),
        httpx.ConnectError("down"),
    ],
)
def test_undelivered_report_is_502(
    org_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    valid_report: dict,
    result: object,
) -> None:
    failing_post(monkeypatch, result)
    response = org_client.post(REPORT, json=valid_report)
    assert response.status_code == 502
    assert response.json() == {"detail": "Report could not be delivered"}


def test_log_has_outcome_but_no_url_or_payload(
    org_client: TestClient, valid_report: dict, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        org_client.post(REPORT, json=valid_report)
    lines = [r.getMessage() for r in caplog.records if r.name == "app.report"]
    assert len(lines) == 1
    assert lines[0].startswith("report: outcome=ok user=")
    logged = caplog.text
    assert "hook-secret-path" not in logged
    assert "18f3a9c2b4d5e6f7" not in logged


def test_report_counts_toward_rate_limit(
    monkeypatch: pytest.MonkeyPatch, webhook: list, valid_report: dict
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    get_settings.cache_clear()
    client = TestClient(create_app(), headers=AUTH_HEADERS)
    assert client.post(REPORT, json=valid_report).status_code == 200
    assert client.post(REPORT, json=valid_report).status_code == 429
    assert len(webhook) == 1


def test_webhook_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOC_WEBHOOK_URL", "http://soc.example.com/hook")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="https"):
        get_settings()


def test_every_catalog_id_is_accepted(org_client: TestClient, valid_report: dict) -> None:
    from app.signals.messages import CATALOG

    valid_report["reason_ids"] = list(CATALOG)[:50]
    assert org_client.post(REPORT, json=valid_report).status_code == 200
