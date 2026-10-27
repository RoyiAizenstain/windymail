"""Settings loaded from environment variables only (ADR-011). No secrets in code."""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

Mode = Literal["organization", "personal"]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    raise ValueError(f"{name} must be true or false")


def _env_positive_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError(f"{name} must be a positive whole number")
    return int(raw)


def _env_str(name: str) -> str | None:
    raw = os.environ.get(name, "").strip()
    return raw or None


def _env_required(name: str) -> str:
    value = _env_str(name)
    if value is None:
        # Fail closed: without it, tokens cannot be checked against our audience.
        raise RuntimeError(f"{name} must be set")
    return value


def _env_https_url(name: str) -> str | None:
    value = _env_str(name)
    if value is not None and not value.lower().startswith("https://"):
        # Reports leave the backend; never send them in clear text.
        raise ValueError(f"{name} must be an https:// URL")
    return value


@dataclass(frozen=True)
class Settings:
    google_client_id: str
    soc_webhook_url: str | None
    enable_api_docs: bool
    # LLM step (ADR-019). Without a key the backend runs deterministic-only (ADR-005).
    anthropic_api_key: str | None = None
    llm_enabled: bool = True
    llm_model: str = "claude-haiku-5-5"
    # Per-user requests per minute (ADR-011); also caps LLM spend per user.
    rate_limit_per_minute: int = 20
    # Score the add-on's attachment facts (ADR-021); off ignores them without a deploy.
    attachment_inspection: bool = True

    @property
    def mode(self) -> Mode:
        # ADR-015: a configured SOC webhook means organization mode.
        return "organization" if self.soc_webhook_url else "personal"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        google_client_id=_env_required("GOOGLE_CLIENT_ID"),
        soc_webhook_url=_env_https_url("SOC_WEBHOOK_URL"),
        enable_api_docs=_env_bool("ENABLE_API_DOCS", default=False),
        anthropic_api_key=_env_str("ANTHROPIC_API_KEY"),
        llm_enabled=_env_bool("LLM_ENABLED", default=True),
        llm_model=_env_str("LLM_MODEL") or "claude-haiku-5-5",
        rate_limit_per_minute=_env_positive_int("RATE_LIMIT_PER_MINUTE", default=20),
        attachment_inspection=_env_bool("ATTACHMENT_INSPECTION", default=True),
    )
