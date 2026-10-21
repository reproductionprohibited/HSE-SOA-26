from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import decode_refresh_token, issue_token_pair
from app.db.models import User
from app.db.session import SessionFactory
from app.errors import ApiError
from marketplace_api.models import ErrorCode, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserRole


async def _find_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(func.lower(User.email) == email.lower()))


class AuthService:
    async def register(self, data: RegisterRequest) -> User:
        password_hash = await hash_password(data.password)
        try:
            async with SessionFactory() as session, session.begin():
                if await _find_by_email(session, data.email) is not None:
                    raise ApiError(ErrorCode.USER_ALREADY_EXISTS, "User with this email already exists", {"email": data.email})
                user = User(email=data.email, password_hash=password_hash, role=UserRole(str(data.role)))
                session.add(user)
        except IntegrityError:
            # Параллельная регистрация того же email — сработал уникальный индекс
            raise ApiError(ErrorCode.USER_ALREADY_EXISTS, "User with this email already exists", {"email": data.email})
        return user

    async def login(self, data: LoginRequest) -> TokenResponse:
        async with SessionFactory() as session:
            user = await _find_by_email(session, data.email)
        if not await verify_password(user.password_hash if user else None, data.password):
            raise ApiError(ErrorCode.INVALID_CREDENTIALS, "Invalid email or password")
        return issue_token_pair(user.id, user.role)

    async def refresh(self, data: RefreshRequest) -> TokenResponse:
        claims = decode_refresh_token(data.refresh_token)
        async with SessionFactory() as session:
            user = await session.get(User, claims.user_id)
        if user is None:
            raise ApiError(ErrorCode.REFRESH_TOKEN_INVALID, "Refresh token is invalid or expired")
        # Роль берётся из БД, а не из старого токена — изменения роли применяются при обновлении
        return issue_token_pair(user.id, user.role)
