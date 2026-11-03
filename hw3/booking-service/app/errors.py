"""Единый формат ошибок REST: {"error": {"code", "message", "details"}}."""

import logging
from typing import Any

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.flight_client.circuit_breaker import CircuitOpenError, retry_after_header

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BookingNotFound(AppError):
    status_code = 404
    code = "BOOKING_NOT_FOUND"

    def __init__(self, booking_id: object) -> None:
        super().__init__(f"booking {booking_id} not found")


class BookingNotCancellable(AppError):
    status_code = 409
    code = "BOOKING_NOT_CANCELLABLE"

    def __init__(self, booking_id: object, status: str) -> None:
        super().__init__(f"booking {booking_id} is {status}, only CONFIRMED bookings can be cancelled")


# gRPC status Flight Service -> (HTTP status, код ошибки REST)
_GRPC_TO_HTTP: dict[grpc.StatusCode, tuple[int, str]] = {
    grpc.StatusCode.INVALID_ARGUMENT: (400, "VALIDATION_ERROR"),
    grpc.StatusCode.NOT_FOUND: (404, "NOT_FOUND"),
    grpc.StatusCode.RESOURCE_EXHAUSTED: (409, "NOT_ENOUGH_SEATS"),
    grpc.StatusCode.FAILED_PRECONDITION: (409, "FLIGHT_NOT_AVAILABLE"),
    grpc.StatusCode.ALREADY_EXISTS: (409, "RESERVATION_ALREADY_EXISTS"),
    grpc.StatusCode.UNAVAILABLE: (503, "FLIGHT_SERVICE_UNAVAILABLE"),
    grpc.StatusCode.DEADLINE_EXCEEDED: (504, "FLIGHT_SERVICE_TIMEOUT"),
}


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(grpc.aio.AioRpcError)
    async def handle_grpc_error(request: Request, exc: grpc.aio.AioRpcError) -> JSONResponse:
        # UNAUTHENTICATED, INTERNAL и прочее — проблема на стороне Flight Service, а не клиента
        status_code, code = _GRPC_TO_HTTP.get(exc.code(), (502, "UPSTREAM_ERROR"))
        logger.warning(
            "flight-service call failed",
            extra={"fields": {"grpc_code": exc.code().name, "grpc_details": exc.details(), "http_status": status_code}},
        )
        return error_response(status_code, code, exc.details() or exc.code().name)

    @app.exception_handler(CircuitOpenError)
    async def handle_circuit_open(request: Request, exc: CircuitOpenError) -> JSONResponse:
        # Мгновенный отказ без вызова Flight Service — клиент не ждёт таймаута
        response = error_response(503, "FLIGHT_SERVICE_UNAVAILABLE", "flight-service is unavailable, try again later")
        response.headers["Retry-After"] = retry_after_header(exc)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return error_response(400, "VALIDATION_ERROR", "request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return error_response(500, "INTERNAL_ERROR", "internal error")
