"""Аутентификация запроса и проверка ролей."""

from fastapi import Request

from app.auth.tokens import Principal, decode_access_token
from app.errors import ApiError
from marketplace_api.models import ErrorCode, UserRole


async def authenticate(request: Request) -> Principal:
    """FastAPI-зависимость для операций с `security: bearerAuth` в контракте."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Missing or malformed Authorization header, expected 'Bearer <token>'")
    principal = decode_access_token(token)
    # Для access-лога: middleware читает user_id из состояния запроса
    request.state.user_id = str(principal.user_id)
    return principal


def require_roles(principal: Principal, *allowed: UserRole) -> None:
    if principal.role not in allowed:
        raise ApiError(
            ErrorCode.ACCESS_DENIED,
            f"Role {principal.role.value} is not allowed to perform this operation",
            {"role": principal.role.value, "allowed_roles": [r.value for r in allowed]},
        )
