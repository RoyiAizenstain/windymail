import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import analyze as real
from app.config import get_settings
from app.main import create_app
from app.security import MAX_REQUEST_BYTES, BodySizeLimit, RateLimiter, hash_user

from .conftest import AUTH_HEADERS

MARKER = "SECRET-BODY-CONTENT"


def sized(valid_request: dict, total: int) -> bytes:
    """A valid analyze request padded to exactly `total` bytes of JSON."""
    base = json.dumps({**valid_request, "body_text": "", "body_html": ""}).encode()
    pad = total - len(base)
    half = pad // 2
    body = {**valid_request, "body_text": MARKER + "x" * (half - len(MARKER)),
            "body_html": "y" * (pad - half)}  # fmt: skip
    data = json.dumps(body).encode()
    assert len(data) == total
    return data


JSON = {"Content-Type": "application/json"}


# Through the app


def test_just_under_the_cap_passes(client: TestClient, valid_request: dict) -> None:
    response = client.post("/api/v1/analyze", content=sized(valid_request, 199_000), headers=JSON)
    assert response.status_code == 200


def test_over_the_cap_is_413(client: TestClient, valid_request: dict) -> None:
    data = sized(valid_request, MAX_REQUEST_BYTES + 1_000)
    response = client.post("/api/v1/analyze", content=data, headers=JSON)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request too large"}
    assert MARKER not in response.text


def test_over_the_cap_without_content_length_is_413(
    client: TestClient, valid_request: dict
) -> None:
    data = sized(valid_request, MAX_REQUEST_BYTES + 1_000)
    chunks = (data[i : i + 16_384] for i in range(0, len(data), 16_384))
    response = client.post("/api/v1/analyze", content=chunks, headers=JSON)  # chunked
    assert response.status_code == 413
    assert MARKER not in response.text


def test_oversized_is_rejected_before_the_token_is_checked(
    anon_client: TestClient, valid_request: dict, verify_calls: list
) -> None:
    data = sized(valid_request, MAX_REQUEST_BYTES + 1)
    response = anon_client.post(
        "/api/v1/analyze", content=data, headers={**JSON, "Authorization": "Bearer valid-token"}
    )
    assert response.status_code == 413
    assert verify_calls == []  # no work, no outbound certificate fetch


def test_health_unaffected(anon_client: TestClient) -> None:
    assert anon_client.get("/health").status_code == 200


# The middleware alone: requests the test client can't produce


def run(middleware: BodySizeLimit, headers: list, chunks: list[bytes]) -> tuple[int, bytes]:
    messages = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
    messages[-1]["more_body"] = False
    sent: list[dict] = []

    async def receive() -> dict:
        return messages.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}
    asyncio.run(middleware(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


async def echo_length(scope, receive, send) -> None:
    """A stand-in app that reads the whole body, then answers 200."""
    size = 0
    while True:
        message = await receive()
        size += len(message.get("body", b""))
        if not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(size).encode()})


def test_false_content_length_is_stopped_while_reading() -> None:
    limit = BodySizeLimit(echo_length, max_bytes=100)
    status, body = run(limit, [(b"content-length", b"10")], [b"a" * 60, b"b" * 60])
    assert (status, body) == (413, b'{"detail":"Request too large"}')


def test_within_limit_reaches_the_app() -> None:
    status, body = run(BodySizeLimit(echo_length, max_bytes=100), [], [b"a" * 50, b"b" * 50])
    assert (status, body) == (200, b"100")


@pytest.mark.parametrize("value", [b"abc", b"-1", b"1e9", b""])
def test_invalid_content_length_is_400(value: bytes) -> None:
    status, _ = run(BodySizeLimit(echo_length), [(b"content-length", value)], [b"x"])
    assert status == 400


# Rate limiting (429)


class Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_limit_then_block_with_retry_after() -> None:
    clock = Clock(1_000.0)  # 40 s into its minute
    limiter = RateLimiter(3, clock=clock)
    assert [limiter.check("u") for _ in range(3)] == [None, None, None]
    assert limiter.check("u") == 20  # seconds until the next window


def test_users_are_counted_separately() -> None:
    limiter = RateLimiter(1, clock=Clock())
    assert limiter.check("a") is None
    assert limiter.check("a") is not None
    assert limiter.check("b") is None


def test_window_resets_and_old_entries_are_dropped() -> None:
    clock = Clock(1_000.0)
    limiter = RateLimiter(1, clock=clock)
    limiter.check("a")
    limiter.check("b")
    assert limiter.check("a") is not None
    clock.now += 60
    assert limiter.check("a") is None
    assert set(limiter._counts) == {"a"}  # b's finished window was dropped


def test_hash_user_is_stable_and_not_the_raw_id() -> None:
    assert hash_user("user-123") == hash_user("user-123")
    assert hash_user("user-123") != hash_user("user-124")
    assert "user-123" not in hash_user("user-123") and len(hash_user("user-123")) == 16


def test_api_returns_429_and_skips_analysis(
    monkeypatch: pytest.MonkeyPatch, valid_request: dict
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr(main, "analyze_email", lambda request: calls.append(1) or real(request))
    client = TestClient(create_app(), headers=AUTH_HEADERS)
    codes = [client.post("/api/v1/analyze", json=valid_request).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert len(calls) == 2  # the blocked request never reached the analysis (or the LLM)
    blocked = client.post("/api/v1/analyze", json=valid_request)
    assert blocked.json() == {"detail": "Too many requests"}
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


def test_rate_limit_setting_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("0", "-5", "abc"):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", bad)
        get_settings.cache_clear()
        with pytest.raises(ValueError):
            get_settings()


def test_invalid_token_is_401_not_counted(anon_client: TestClient, valid_request: dict) -> None:
    headers = {"Authorization": "Bearer wrong"}
    codes = {anon_client.post("/api/v1/analyze", json=valid_request, headers=headers).status_code
             for _ in range(25)}  # fmt: skip
    assert codes == {401}


# Errors never echo input (422, 500)


@pytest.mark.parametrize(
    "change",
    [
        {"evil_field_" + "x" * 50: MARKER},  # unknown field, attacker-chosen name
        {"subject": MARKER * 200},  # over-long field
        {"truncated": MARKER},  # wrong type
    ],
)
def test_422_does_not_echo_input(client: TestClient, valid_request: dict, change: dict) -> None:
    response = client.post("/api/v1/analyze", json={**valid_request, **change})
    assert response.status_code == 422
    assert MARKER not in response.text and "evil_field" not in response.text
    for error in response.json()["detail"]:
        assert set(error) == {"loc", "type"}


def test_422_keeps_useful_location(client: TestClient, valid_request: dict) -> None:
    response = client.post("/api/v1/analyze", json={**valid_request, "truncated": "maybe"})
    assert response.json() == {"detail": [{"loc": ["body", "truncated"], "type": "bool_parsing"}]}


def test_invalid_json_does_not_echo(client: TestClient) -> None:
    response = client.post("/api/v1/analyze", content=b'{"a": "' + MARKER.encode(), headers=JSON)
    assert response.status_code == 422 and MARKER not in response.text


def test_crash_is_generic_500_logged_by_type_only(
    monkeypatch: pytest.MonkeyPatch, valid_request: dict, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(request):
        raise RuntimeError(MARKER)

    monkeypatch.setattr(main, "analyze_email", boom)
    client = TestClient(create_app(), headers=AUTH_HEADERS)
    response = client.post("/api/v1/analyze", json=valid_request)
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal error"}
    assert "RuntimeError" in caplog.text and MARKER not in caplog.text
