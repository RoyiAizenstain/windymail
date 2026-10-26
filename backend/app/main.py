"""WindyMail backend: FastAPI entry point.

/analyze runs the deterministic checks (Layers 2-3) and scores them provisionally
(ADR-010). Reasons use fixed wording; only normalized values are echoed (ADR-017).
"""

from typing import Annotated

from fastapi import Depends, FastAPI

from app.auth import require_user
from app.config import get_settings
from app.models import AnalyzeRequest, AnalyzeResponse, HealthResponse
from app.scoring import provisional_score
from app.signals import language
from app.signals.engine import run_checks, summarize
from app.verdict import verdict_for


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
        reasons = run_checks(request)
        score = provisional_score(reasons)
        return AnalyzeResponse(
            score=score,
            verdict=verdict_for(score),
            summary=summarize(reasons),
            reasons=reasons,
            manipulation=language.labels(request),
            mode=get_settings().mode,
        )

    return app


app = create_app()
