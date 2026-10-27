import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import AnalyzeResponse
from tests.conftest import AUTH_HEADERS

ANALYZE = "/api/v1/analyze"


def test_health_returns_fixed_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_accepts_head(anon_client: TestClient) -> None:
    response = anon_client.head("/health")
    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize("name", ["wordmark.png", "safe.png", "suspicious.png", "malicious.png"])
def test_card_images_served_without_token(anon_client: TestClient, name: str) -> None:
    response = anon_client.get(f"/static/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "path",
    [
        "/static/other.png",
        "/static/..%2Fapp%2Fmain.py",
        "/static/%2E%2E%2Frequirements.txt",
        "/static/../requirements.txt",
        "/static/",
    ],
)
def test_only_listed_images_are_served(anon_client: TestClient, path: str) -> None:
    response = anon_client.get(path)
    assert response.status_code == 404
    assert b"fastapi" not in response.content


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


def test_analyze_accepts_truncated_flag(client: TestClient, valid_request: dict) -> None:
    valid_request["truncated"] = True
    assert client.post(ANALYZE, json=valid_request).status_code == 200


def test_analyze_rejects_non_boolean_truncated(client: TestClient, valid_request: dict) -> None:
    valid_request["truncated"] = "yes please"
    assert client.post(ANALYZE, json=valid_request).status_code == 422


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
    client = TestClient(create_app(), headers=AUTH_HEADERS)
    assert client.post(ANALYZE, json=valid_request).json()["mode"] == "organization"


def test_api_docs_disabled_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_docs_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 200
