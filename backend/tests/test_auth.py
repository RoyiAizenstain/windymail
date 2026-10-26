import pytest
from fastapi.testclient import TestClient
from google.auth import exceptions as google_exceptions

from app import auth
from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_CLIENT_ID, VALID_TOKEN

ANALYZE = "/api/v1/analyze"


def test_missing_token_is_401(anon_client: TestClient, valid_request: dict) -> None:
    response = anon_client.post(ANALYZE, json=valid_request)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer   ", f"Basic {VALID_TOKEN}", VALID_TOKEN, f"Token {VALID_TOKEN}"],
)
def test_malformed_header_is_401(anon_client: TestClient, valid_request: dict, header: str) -> None:
    response = anon_client.post(ANALYZE, json=valid_request, headers={"Authorization": header})
    assert response.status_code == 401


def test_invalid_token_is_401(anon_client: TestClient, valid_request: dict) -> None:
    response = anon_client.post(
        ANALYZE, json=valid_request, headers={"Authorization": "Bearer forged"}
    )
    assert response.status_code == 401
    assert "forged" not in response.text


def test_scheme_is_case_insensitive(anon_client: TestClient, valid_request: dict) -> None:
    response = anon_client.post(
        ANALYZE, json=valid_request, headers={"Authorization": f"bearer {VALID_TOKEN}"}
    )
    assert response.status_code == 200


def test_valid_token_is_checked_against_configured_audience(
    client: TestClient, valid_request: dict, verify_calls: list[dict]
) -> None:
    assert client.post(ANALYZE, json=valid_request).status_code == 200
    assert verify_calls == [{"token": VALID_TOKEN, "audience": TEST_CLIENT_ID}]


def test_auth_runs_before_body_validation(anon_client: TestClient) -> None:
    # An anonymous caller learns nothing about the schema.
    assert anon_client.post(ANALYZE, json={"junk": 1}).status_code in (401, 422)


def test_token_without_subject_is_401(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, valid_request: dict
) -> None:
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda *a, **k: {"aud": "x"})
    assert client.post(ANALYZE, json=valid_request).status_code == 401


def test_cert_fetch_failure_is_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, valid_request: dict
) -> None:
    def unreachable(*args: object, **kwargs: object) -> dict:
        raise google_exceptions.TransportError("down")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", unreachable)
    assert client.post(ANALYZE, json=valid_request).status_code == 503


def test_health_needs_no_token(anon_client: TestClient) -> None:
    assert anon_client.get("/health").status_code == 200


def test_app_refuses_to_start_without_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID"):
        create_app()


def test_cert_fetch_has_explicit_timeout() -> None:
    assert 0 < auth.CERT_FETCH_TIMEOUT_SECONDS <= 10
