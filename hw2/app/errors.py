"""Единый формат ошибок API (ErrorResponse из контракта) и обработчики исключений."""

import logging
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from marketplace_api.models import ErrorCode, ErrorResponse

logger = logging.getLogger(__name__)

HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.PRODUCT_NOT_FOUND: 404,
    ErrorCode.PRODUCT_INACTIVE: 409,
    ErrorCode.ORDER_NOT_FOUND: 404,
    ErrorCode.ORDER_LIMIT_EXCEEDED: 429,
    ErrorCode.ORDER_HAS_ACTIVE: 409,
    ErrorCode.INVALID_STATE_TRANSITION: 409,
    ErrorCode.INSUFFICIENT_STOCK: 409,
    ErrorCode.PROMO_CODE_INVALID: 422,
    ErrorCode.PROMO_CODE_MIN_AMOUNT: 422,
    ErrorCode.PROMO_CODE_ALREADY_EXISTS: 409,
    ErrorCode.ORDER_OWNERSHIP_VIOLATION: 403,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.REFRESH_TOKEN_INVALID: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.USER_ALREADY_EXISTS: 409,
    ErrorCode.ACCESS_DENIED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.INTERNAL_ERROR: 500,
}


class ApiError(Exception):
    """Бизнес-ошибка: бросается из сервисов, превращается в ErrorResponse."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    @property
    def status_code(self) -> int:
        return HTTP_STATUS[self.code]


def error_response(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorResponse(error_code=code, message=message, details=details)
    content = jsonable_encoder(body.model_dump(mode="python"), custom_encoder={Decimal: float})
    return JSONResponse(content=content, status_code=HTTP_STATUS[code])


def _format_loc(loc: tuple[int | str, ...]) -> str:
    # ('body', 'items', 0, 'quantity') -> 'body.items[0].quantity'
    result = ""
    for part in loc:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}" if result else str(part)
    return result


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for err in exc.errors():
        if err["type"] == "json_invalid":
            # loc = ('body', <позиция в строке>) — показываем позицию в сообщении
            field = "body"
            message = f"Invalid JSON at position {err['loc'][-1]}: {err['ctx']['error']}"
        else:
            field = _format_loc(err["loc"])
            message = err["msg"]
        fields.append({"field": field, "message": message, "type": err["type"]})
    return error_response(ErrorCode.VALIDATION_ERROR, "Request validation failed", {"fields": fields})


async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response(ErrorCode.NOT_FOUND, "Resource not found")
    if exc.status_code == 405:
        return error_response(ErrorCode.METHOD_NOT_ALLOWED, "Method not allowed")
    if exc.status_code == 400:
        return error_response(ErrorCode.VALIDATION_ERROR, str(exc.detail))
    return error_response(ErrorCode.INTERNAL_ERROR, str(exc.detail))


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return error_response(ErrorCode.INTERNAL_ERROR, "Internal server error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
