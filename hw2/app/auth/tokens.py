"""JWT: access (короткоживущий) и refresh (долгоживущий) токены.

Оба подписаны HS256 и различаются claim'ом `type`, поэтому refresh token
нельзя использовать как access и наоборот.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.errors import ApiError
from marketplace_api.models import ErrorCode, TokenResponse, UserRole

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"
REQUIRED_CLAIMS = ["sub", "role", "type", "iat", "exp"]


@dataclass(frozen=True)
class Principal:
    """Аутентифицированный пользователь — из claims access token."""

    user_id: uuid.UUID
    role: UserRole


def _issue(user_id: uuid.UUID, role: UserRole, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def issue_token_pair(user_id: uuid.UUID, role: UserRole) -> TokenResponse:
    access_ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    return TokenResponse(
        access_token=_issue(user_id, role, ACCESS, access_ttl),
        refresh_token=_issue(user_id, role, REFRESH, timedelta(days=settings.refresh_token_ttl_days)),
        token_type="Bearer",
        expires_in=int(access_ttl.total_seconds()),
    )


def _decode(token: str, token_type: str) -> Principal:
    """Бросает jwt.ExpiredSignatureError для истёкшего токена и jwt.InvalidTokenError для любого другого дефекта."""
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": REQUIRED_CLAIMS})
    if claims["type"] != token_type:
        raise jwt.InvalidTokenError(f"Expected {token_type} token")
    try:
        return Principal(user_id=uuid.UUID(claims["sub"]), role=UserRole(claims["role"]))
    except ValueError as e:
        raise jwt.InvalidTokenError(str(e)) from e


def decode_access_token(token: str) -> Principal:
    try:
        return _decode(token, ACCESS)
    except jwt.ExpiredSignatureError:
        raise ApiError(ErrorCode.TOKEN_EXPIRED, "Access token has expired")
    except jwt.InvalidTokenError:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Access token is invalid")


def decode_refresh_token(token: str) -> Principal:
    try:
        return _decode(token, REFRESH)
    except jwt.InvalidTokenError:  # включая истёкший
        raise ApiError(ErrorCode.REFRESH_TOKEN_INVALID, "Refresh token is invalid or expired")
