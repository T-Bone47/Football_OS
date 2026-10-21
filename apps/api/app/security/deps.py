"""FastAPI adapters over app.security.tokens (kept thin; logic lives in tokens.py)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.config import get_settings
from app.security.revocation import get_revocations
from app.security.tokens import AuthError, Principal, extract_bearer, require_permission, verify_token


def _http(exc: AuthError) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return HTTPException(status_code=exc.status_code, detail=exc.detail, headers=headers)


def get_principal(request: Request) -> Principal:
    settings = get_settings()
    token = extract_bearer(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(
            status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        return verify_token(
            token,
            secret=settings.auth_jwt_secret,
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            previous_secrets=tuple(x for x in (settings.auth_jwt_secret_previous,) if x),
            revocations=get_revocations(),
        )
    except AuthError as exc:
        raise _http(exc) from exc


def require(permission: str):
    """Dependency factory: authenticated AND holding `permission`."""

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        try:
            require_permission(principal, permission)
        except AuthError as exc:
            raise _http(exc) from exc
        return principal

    return dependency
