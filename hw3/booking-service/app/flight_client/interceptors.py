"""Client interceptors канала к Flight Service.

Порядок в канале: CircuitBreaker -> Retry -> ApiKey -> сеть. Breaker видит один логический вызов
(после всех повторов), а в состоянии OPEN до retry дело не доходит.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

import grpc

from app.flight_client.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-api-key"

# Сбои инфраструктуры: вызов мог не дойти до сервиса или не завершиться
RETRYABLE_CODES = frozenset({grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED})
BREAKER_FAILURE_CODES = RETRYABLE_CODES | {grpc.StatusCode.INTERNAL, grpc.StatusCode.UNKNOWN}

type Continuation = Callable[[grpc.aio.ClientCallDetails, Any], Any]


def _method(details: grpc.aio.ClientCallDetails) -> str:
    method = details.method
    return method.decode() if isinstance(method, bytes) else method


class ApiKeyInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Добавляет API key в metadata каждого вызова — бизнес-код о ключе не знает."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def intercept_unary_unary(
        self, continuation: Continuation, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        metadata = grpc.aio.Metadata(*(client_call_details.metadata or ()))
        metadata.add(API_KEY_HEADER, self._api_key)
        return await continuation(client_call_details._replace(metadata=metadata), request)  # pyright: ignore[reportAttributeAccessIssue]


class RetryInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Повторяет вызов при UNAVAILABLE / DEADLINE_EXCEEDED с exponential backoff.

    Повторять безопасно все методы: чтения идемпотентны, ReserveSeats — по booking_id,
    ReleaseReservation — по статусу резервации. У каждой попытки свой deadline.
    """

    def __init__(self, max_attempts: int, initial_backoff_ms: int) -> None:
        self._max_attempts = max_attempts
        self._initial_backoff = initial_backoff_ms / 1000

    async def intercept_unary_unary(
        self, continuation: Continuation, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        method = _method(client_call_details)
        for attempt in range(1, self._max_attempts + 1):
            try:
                call = await continuation(client_call_details, request)
                return await call
            except grpc.aio.AioRpcError as exc:
                if exc.code() not in RETRYABLE_CODES:
                    raise
                if attempt == self._max_attempts:
                    logger.warning(
                        "flight-service call failed, retries exhausted",
                        extra={"fields": {"method": method, "attempts": attempt, "grpc_code": exc.code().name}},
                    )
                    raise
                backoff = self._backoff(attempt)
                logger.info(
                    "retrying flight-service call",
                    extra={
                        "fields": {
                            "method": method,
                            "attempt": attempt,
                            "max_attempts": self._max_attempts,
                            "grpc_code": exc.code().name,
                            "backoff_ms": round(backoff * 1000),
                        }
                    },
                )
                await asyncio.sleep(backoff)
        raise AssertionError("unreachable")

    def _backoff(self, attempt: int) -> float:
        # 100 мс, 200 мс, 400 мс, ... ± 20% — чтобы повторы разных клиентов не совпадали
        return self._initial_backoff * 2 ** (attempt - 1) * random.uniform(0.8, 1.2)


class CircuitBreakerInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """В состоянии OPEN вызов завершается CircuitOpenError сразу, без обращения к сети."""

    def __init__(self, breaker: CircuitBreaker) -> None:
        self._breaker = breaker

    async def intercept_unary_unary(
        self, continuation: Continuation, client_call_details: grpc.aio.ClientCallDetails, request: Any
    ) -> Any:
        self._breaker.before_call()  # CircuitOpenError в OPEN
        try:
            call = await continuation(client_call_details, request)
            response = await call
        except grpc.aio.AioRpcError as exc:
            # Бизнес-ошибки (NOT_FOUND, RESOURCE_EXHAUSTED, ...) — сервис жив и ответил
            if exc.code() in BREAKER_FAILURE_CODES:
                self._breaker.record_failure(f"{_method(client_call_details)} {exc.code().name}")
            else:
                self._breaker.record_success()
            raise
        except BaseException:
            # Отмена запроса клиентом и т.п. — о состоянии сервиса ничего не говорит
            self._breaker.release_probe()
            raise
        self._breaker.record_success()
        return response
