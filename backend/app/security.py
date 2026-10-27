"""Request-level protections (ADR-011, Layer 4).

Whole-request size cap: rejected from `Content-Length` before the body is read, and
counted again while reading, so a request without `Content-Length` (chunked) or with a
false one is stopped at the limit too. The add-on keeps requests under 190 KB, so
normal use never reaches it.

Rate limit: fixed window per hashed user, checked right after the token and before
any analysis, so it also caps LLM spend per user. In memory, single instance; it
resets on restart (documented limitation).

Errors never echo input: a 422 says where and what kind, never the submitted value;
an unexpected error is a generic 500 with only its type logged.
"""

import hashlib
import logging
import math
import re
import secrets
import threading
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import require_user

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 200_000
WINDOW_SECONDS = 60

# Generated at startup, never stored or logged: hashes mean nothing outside this process.
_SALT = secrets.token_bytes(32)


def hash_user(sub: str) -> str:
    return hashlib.sha256(_SALT + sub.encode()).hexdigest()[:16]


class RateLimiter:
    """Fixed window per key. Thread-safe: sync endpoints run in a thread pool."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, int]] = {}  # key -> (window, count)
        self._current_window = -1

    def check(self, key: str) -> int | None:
        """Counts one request; returns seconds to wait if over the limit, else None."""
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        with self._lock:
            if window != self._current_window:
                # Drop finished windows, so memory stays bounded by active users.
                self._counts = {k: v for k, v in self._counts.items() if v[0] == window}
                self._current_window = window
            _, count = self._counts.get(key, (window, 0))
            if count >= self.limit:
                return max(1, math.ceil((window + 1) * WINDOW_SECONDS - now))
            self._counts[key] = (window, count + 1)
            return None


def rate_limited_user(request: Request, user_id: Annotated[str, Depends(require_user)]) -> str:
    """The verified user, hashed, if within the rate limit; otherwise 429."""
    hashed = hash_user(user_id)
    request.state.user_hash = hashed  # for the request log
    retry_after = request.app.state.rate_limiter.check(hashed)
    if retry_after is not None:
        logger.info("rate_limit: user=%s blocked retry_after=%d", hashed, retry_after)
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )
    return hashed


_SAFE_LOC = re.compile(r"[a-z_]{1,40}")


def _safe_loc(part: object) -> object:
    # Field names in `loc` can come from the request (an unknown field), so only short
    # known-looking names and list positions pass.
    if isinstance(part, int):
        return part
    return part if isinstance(part, str) and _SAFE_LOC.fullmatch(part) else "?"


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {"loc": [_safe_loc(p) for p in error.get("loc", ())], "type": str(error.get("type"))}
        for error in exc.errors()
    ]
    return JSONResponse({"detail": detail}, status_code=422)


class ErrorShield:
    """Outermost: any unhandled error becomes a generic 500, logged by type only.

    Catching here, rather than letting the server log the traceback, keeps exception
    messages (which can hold request content) out of the logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # noqa: BLE001 - the point is to catch everything
            logger.error("error: type=%s path=%s", type(exc).__name__, scope.get("path"))
            if not started:
                await JSONResponse({"detail": "Internal error"}, 500)(scope, receive, send)


_TOO_LARGE = {"detail": "Request too large"}


class RequestTooLarge(HTTPException):
    # An HTTPException, so FastAPI passes it through while reading the body instead
    # of turning it into a generic 400.
    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_TOO_LARGE["detail"])


class BodySizeLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            if not declared.isdigit():
                await JSONResponse({"detail": "Bad request"}, 400)(scope, receive, send)
                return
            if int(declared) > self.max_bytes:
                await JSONResponse(_TOO_LARGE, 413)(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestTooLarge:
            # Raised outside a route (e.g. by another middleware reading the body).
            if not started:
                await JSONResponse(_TOO_LARGE, 413)(scope, receive, send)
