import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.routes import bookings_router, flights_router
from app.config import settings
from app.db.session import engine
from app.errors import register_error_handlers
from app.flight_client.circuit_breaker import CircuitBreaker
from app.flight_client.client import FlightClient
from app.logging_config import setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    breaker = CircuitBreaker(
        settings.cb_failure_threshold, settings.cb_window_seconds, settings.cb_open_timeout_seconds
    )
    app.state.flight_client = FlightClient(
        settings.flight_service_addr,
        settings.flight_service_timeout_seconds,
        settings.flight_service_api_key,
        breaker,
        settings.retry_max_attempts,
        settings.retry_initial_backoff_ms,
    )
    logger.info("booking-service started", extra={"fields": {"flight_service_addr": settings.flight_service_addr}})
    yield
    await app.state.flight_client.close()
    await engine.dispose()


app = FastAPI(title="Booking Service", version="1.0.0", lifespan=lifespan)
app.include_router(flights_router)
app.include_router(bookings_router)
register_error_handlers(app)


@app.middleware("http")
async def access_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "http request",
        extra={
            "fields": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        },
    )
    return response
