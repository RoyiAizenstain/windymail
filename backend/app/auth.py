"""Google ID token verification (ADR-011).

Every protected endpoint requires `Authorization: Bearer <Google ID token>`. The
token's signature, issuer, expiry, and audience are verified with google-auth.
Failures return 401 without detail; the token is never logged.
"""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Explicit timeout on the outbound fetch of Google's signing certificates (ADR-011).
CERT_FETCH_TIMEOUT_SECONDS = 5


class _TimeoutRequest(google_requests.Request):
    def __call__(self, *args, **kwargs):  # type: ignore[override]
        kwargs["timeout"] = CERT_FETCH_TIMEOUT_SECONDS
        return super().__call__(*args, **kwargs)


_transport = _TimeoutRequest()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Unauthorized",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise _UNAUTHORIZED
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _UNAUTHORIZED
    return token.strip()


def require_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Returns the verified Google user ID (`sub`). Never log or store it in clear."""
    token = _bearer_token(authorization)
    try:
        claims = id_token.verify_oauth2_token(token, _transport, audience=settings.google_client_id)
    except google_exceptions.TransportError:
        logger.error("auth: could not fetch Google signing certificates")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable"
        ) from None
    except (ValueError, google_exceptions.GoogleAuthError):
        logger.info("auth: token rejected")
        raise _UNAUTHORIZED from None

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _UNAUTHORIZED
    return sub
