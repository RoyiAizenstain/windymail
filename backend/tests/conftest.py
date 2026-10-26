from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Tests never depend on the developer's shell or .env.
    for name in ("SOC_WEBHOOK_URL", "ENABLE_API_DOCS"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
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
