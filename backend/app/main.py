"""WindyMail backend: FastAPI entry point.

Layer 1: /analyze returns a fixed mock in the final response schema. Nothing from
the request is echoed back.
"""

from typing import Annotated

from fastapi import Depends, FastAPI

from app.auth import require_user
from app.config import get_settings
from app.models import AnalyzeRequest, AnalyzeResponse, HealthResponse, Reason
from app.verdict import verdict_for

MOCK_SCORE = 42


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.enable_api_docs
    app = FastAPI(
        title="WindyMail",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    @app.api_route("/health", methods=["GET", "HEAD"])
    def health() -> HealthResponse:
        # Keep-warm target (ADR-012): fixed response, no version or config.
        # HEAD too: uptime monitors (UptimeRobot) probe with HEAD by default.
        return HealthResponse(status="ok")

    @app.post("/api/v1/analyze")
    def analyze(
        request: AnalyzeRequest, user_id: Annotated[str, Depends(require_user)]
    ) -> AnalyzeResponse:
        return AnalyzeResponse(
            score=MOCK_SCORE,
            verdict=verdict_for(MOCK_SCORE),
            summary="Mock result: the connection works, real analysis is not built yet.",
            reasons=[
                Reason(
                    id="mock_reason",
                    category="content",
                    severity="low",
                    text="This is a placeholder reason from the WindyMail backend.",
                    details="Layer 1 mock. No analysis was performed.",
                )
            ],
            manipulation=[],
            mode=get_settings().mode,
        )

    return app


app = create_app()
