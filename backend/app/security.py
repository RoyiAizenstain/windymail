"""Request-level protections (ADR-011, Layer 4).

Whole-request size cap: rejected from `Content-Length` before the body is read, and
counted again while reading, so a request without `Content-Length` (chunked) or with a
false one is stopped at the limit too. The add-on keeps requests under 190 KB, so
normal use never reaches it.
"""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES = 200_000

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
