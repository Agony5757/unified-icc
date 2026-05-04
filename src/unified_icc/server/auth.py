"""API key authentication for the unified-icc server."""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from unified_icc.utils.config import config

_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str | None:
    """FastAPI dependency: verify Bearer token against ICC_API_KEY.

    Returns None when no API key is configured (auth disabled).
    Raises 401 when key is configured but credentials are missing/invalid.
    """
    if not config.api_key:
        return None

    if credentials is None or credentials.credentials != config.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    return credentials.credentials


async def verify_ws_token(token: str | None) -> str | None:
    """WebSocket authentication: verify token query parameter.

    Returns None when no API key is configured (auth disabled).
    Raises ValueError when key is configured but token is missing/invalid.
    """
    if not config.api_key:
        return None

    if token is None or token != config.api_key:
        raise ValueError("Invalid or missing API key")

    return token
