from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param


def is_session_authenticated(authorization: str | None, expected: str) -> bool:
    scheme, credentials = get_authorization_scheme_param(authorization)
    return (
        scheme.lower() == "bearer"
        and bool(credentials)
        and secrets.compare_digest(credentials, expected)
    )


def require_session(request: Request) -> None:
    expected = request.app.state.settings.session_token
    if not is_session_authenticated(request.headers.get("Authorization"), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
