import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import AnalyzeResponse

ANALYZE = "/api/v1/analyze"


def test_health_returns_fixed_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_valid_response(client: TestClient, valid_request: dict) -> None:
    response = client.post(ANALYZE, json=valid_request)
    assert response.status_code == 200
    body = AnalyzeResponse.model_validate(response.json())
    assert 0 <= body.score <= 100
    assert body.mode == "personal"


def test_analyze_does_not_echo_request_content(client: TestClient, valid_request: dict) -> None:
    valid_request["subject"] = "UNIQUE-MARKER-7f3a"
    response = client.post(ANALYZE, json=valid_request)
    assert "UNIQUE-MARKER-7f3a" not in response.text


def test_analyze_rejects_unknown_field(client: TestClient, valid_request: dict) -> None:
    valid_request["unexpected"] = "x"
    assert client.post(ANALYZE, json=valid_request).status_code == 422


def test_analyze_rejects_unknown_attachment_field(client: TestClient, valid_request: dict) -> None:
    valid_request["attachments"][0]["content"] = "base64..."
    assert client.post(ANALYZE, json=valid_request).status_code == 422


@pytest.mark.parametrize("field", ["message_id", "from", "subject", "body_text"])
def test_analyze_rejects_missing_required_field(
    client: TestClient, valid_request: dict, field: str
) -> None:
    del valid_request[field]
    assert client.post(ANALYZE, json=valid_request).status_code == 422


def test_analyze_rejects_overlong_field(client: TestClient, valid_request: dict) -> None:
    valid_request["subject"] = "a" * 2_001
    assert client.post(ANALYZE, json=valid_request).status_code == 422


def test_analyze_rejects_negative_attachment_size(client: TestClient, valid_request: dict) -> None:
    valid_request["attachments"][0]["size_bytes"] = -1
    assert client.post(ANALYZE, json=valid_request).status_code == 422


def test_organization_mode_when_webhook_configured(
    monkeypatch: pytest.MonkeyPatch, valid_request: dict
) -> None:
    monkeypatch.setenv("SOC_WEBHOOK_URL", "https://soc.example.com/hook")
    client = TestClient(create_app())
    assert client.post(ANALYZE, json=valid_request).json()["mode"] == "organization"


def test_api_docs_disabled_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_docs_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 200
