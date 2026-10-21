"""Хеширование паролей (argon2id). Хеширование выполняется в пуле потоков потому что CPU-bound."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

_hasher = PasswordHasher()

# Проверка против фиктивного хеша, когда пользователь не найден: время ответа
# на логин не выдаёт, зарегистрирован ли email
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    def verify() -> bool:
        try:
            return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
        except (VerificationError, InvalidHashError):
            return False

    return await run_in_threadpool(verify)
