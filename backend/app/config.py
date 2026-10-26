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


def _env_str(name: str) -> str | None:
    raw = os.environ.get(name, "").strip()
    return raw or None


@dataclass(frozen=True)
class Settings:
    soc_webhook_url: str | None
    enable_api_docs: bool

    @property
    def mode(self) -> Mode:
        # ADR-015: a configured SOC webhook means organization mode.
        return "organization" if self.soc_webhook_url else "personal"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        soc_webhook_url=_env_str("SOC_WEBHOOK_URL"),
        enable_api_docs=_env_bool("ENABLE_API_DOCS", default=False),
    )
