import os
from collections.abc import Iterator

TEST_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
# app.main builds the app at import time and fails closed without a client ID.
os.environ["GOOGLE_CLIENT_ID"] = TEST_CLIENT_ID

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

VALID_TOKEN = "valid-token"  # noqa: S105 - fake token accepted by fake_verify only
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Tests never depend on the developer's shell or .env.
    # No real LLM call either: tests that need one install a fake client.
    for name in ("SOC_WEBHOOK_URL", "ENABLE_API_DOCS", "ANTHROPIC_API_KEY", "LLM_ENABLED",
                 "LLM_MODEL"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", TEST_CLIENT_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def verify_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replaces Google's verifier: accepts VALID_TOKEN only, records each call."""
    calls: list[dict] = []

    def fake_verify(token: str, request: object, audience: str | None = None) -> dict:
        calls.append({"token": token, "audience": audience})
        if token != VALID_TOKEN:
            raise ValueError("invalid token")
        return {"sub": "user-123", "aud": audience}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    return calls


@pytest.fixture
def client() -> TestClient:
    """Authenticated client: sends a token the fake verifier accepts."""
    return TestClient(create_app(), headers=AUTH_HEADERS)


@pytest.fixture
def anon_client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def valid_request() -> dict:
    return {
        "message_id": "msg-123",
        "from": "Alice <alice@example.com>",
        "reply_to": None,
        "subject": "Hello",
        "auth_results": None,
        "body_text": "Hi there",
        "body_html": None,
        "attachments": [
            {"filename": "report.pdf", "mime_type": "application/pdf", "size_bytes": 1024}
        ],
    }
