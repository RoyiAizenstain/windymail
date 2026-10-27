"""WindyMail backend: FastAPI entry point.

/analyze runs the rules and the bounded LLM step (app/analysis.py) and scores them
provisionally (ADR-010, ADR-019). Reasons use fixed wording; only normalized values
are echoed (ADR-017).
"""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from app.analysis import analyze as analyze_email
from app.config import get_settings
from app.models import AnalyzeRequest, AnalyzeResponse, HealthResponse
from app.security import (
    AccessLog,
    BodySizeLimit,
    ErrorShield,
    RateLimiter,
    rate_limited_user,
    validation_error_handler,
)


def _configure_logging() -> None:
    # Uvicorn configures only its own loggers; without this, our INFO lines (the LLM
    # outcome and latency) are dropped. Content is never logged (ADR-011).
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Replaced by app.access, which leaves out client IPs and query strings (ADR-011).
    logging.getLogger("uvicorn.access").disabled = True


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    docs_enabled = settings.enable_api_docs
    app = FastAPI(
        title="WindyMail",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    # Middleware added last runs first: AccessLog sees every request, ErrorShield turns
    # any crash into a 500 inside it, then the size cap runs before anything reads the
    # body (ADR-011).
    app.add_middleware(BodySizeLimit)
    app.add_middleware(ErrorShield)
    app.add_middleware(AccessLog)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    # Per app instance, so each test client starts with fresh counters.
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.api_route("/health", methods=["GET", "HEAD"])
    def health() -> HealthResponse:
        # Keep-warm target (ADR-012): fixed response, no version or config.
        # HEAD too: uptime monitors (UptimeRobot) probe with HEAD by default.
        return HealthResponse(status="ok")

    @app.post("/api/v1/analyze")
    def analyze(
        request: AnalyzeRequest, user_hash: Annotated[str, Depends(rate_limited_user)]
    ) -> AnalyzeResponse:
        return analyze_email(request)

    return app


app = create_app()
