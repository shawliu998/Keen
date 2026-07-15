from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param


def require_session(request: Request) -> None:
    scheme, credentials = get_authorization_scheme_param(
        request.headers.get("Authorization")
    )
    expected = request.app.state.settings.session_token
    authenticated = (
        scheme.lower() == "bearer"
        and bool(credentials)
        and secrets.compare_digest(credentials, expected)
    )
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
