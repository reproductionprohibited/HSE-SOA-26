"""Cache-aside для рейсов и результатов поиска. Значения — сериализованные protobuf-сообщения."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import cast

from google.protobuf.message import Message
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def flight_key(flight_id: uuid.UUID) -> str:
    return f"flight:{flight_id}"


def search_key(origin: str, destination: str, departure_date: date | None) -> str:
    return f"search:{origin}:{destination}:{departure_date.isoformat() if departure_date else 'any'}"


class FlightCache:
    def __init__(self, redis: Redis, flight_ttl_seconds: int, search_ttl_seconds: int) -> None:
        self._redis = redis
        self.flight_ttl = flight_ttl_seconds
        self.search_ttl = search_ttl_seconds

    async def get_or_load[M: Message](
        self, key: str, ttl: int, message_type: type[M], load: Callable[[], Awaitable[M]]
    ) -> M:
        """Кеш -> при miss загрузка из БД -> запись в кеш с TTL.

        Исключение из load (например, рейс не найден) пробрасывается и не кешируется.
        """
        cached = await self._get(key)
        if cached is not None:
            logger.info("cache hit", extra={"fields": {"key": key}})
            return message_type.FromString(cached)

        logger.info("cache miss", extra={"fields": {"key": key}})
        message = await load()
        await self._set(key, message.SerializeToString(), ttl)
        return message

    async def invalidate_flight(
        self, flight_id: uuid.UUID, origin: str, destination: str, *departure_times: datetime
    ) -> None:
        """Удаляет рейс и все результаты поиска, в которые он мог попасть.

        Ключи поиска вычисляются из полей рейса, поэтому SCAN по шаблону не нужен.
        Несколько departure_times — когда дата вылета изменилась (старая и новая).
        """
        keys = {flight_key(flight_id), search_key(origin, destination, None)}
        keys |= {search_key(origin, destination, t.astimezone(UTC).date()) for t in departure_times}
        try:
            await self._redis.delete(*keys)
        except RedisError as exc:
            # Не удалили — устаревшее значение доживёт до TTL
            logger.warning("cache invalidation failed", extra={"fields": {"keys": sorted(keys), "error": str(exc)}})
            return
        logger.info("cache invalidated", extra={"fields": {"keys": sorted(keys)}})

    async def _get(self, key: str) -> bytes | None:
        try:
            # decode_responses=False (по умолчанию) — Redis отдаёт bytes
            return cast(bytes | None, await self._redis.get(key))
        except RedisError as exc:
            logger.warning("cache unavailable, reading from db", extra={"fields": {"key": key, "error": str(exc)}})
            return None

    async def _set(self, key: str, value: bytes, ttl: int) -> None:
        # Единственная точка записи в кеш — TTL обязателен, бесконечных ключей нет
        try:
            await self._redis.set(key, value, ex=ttl)
        except RedisError as exc:
            logger.warning("cache write failed", extra={"fields": {"key": key, "error": str(exc)}})
