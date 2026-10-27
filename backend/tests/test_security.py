import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.security import MAX_REQUEST_BYTES, BodySizeLimit

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
