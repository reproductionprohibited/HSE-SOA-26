"""Аутентификация межсервисных вызовов: API key в metadata `x-api-key`."""

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import grpc

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-api-key"


class ApiKeyAuthInterceptor(grpc.aio.ServerInterceptor):
    """Проверяет ключ для всех методов сервера (включая reflection)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.encode()

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        handler = await continuation(handler_call_details)
        if handler is None or self._is_authorized(handler_call_details):
            return handler

        method = handler_call_details.method  # pyright: ignore[reportAttributeAccessIssue]
        logger.warning("unauthenticated call rejected", extra={"fields": {"method": method}})
        return _reject(handler)

    def _is_authorized(self, details: grpc.HandlerCallDetails) -> bool:
        metadata = details.invocation_metadata or ()  # pyright: ignore[reportAttributeAccessIssue]
        provided = next((value for key, value in metadata if key == API_KEY_HEADER), None)
        if not provided:
            return False
        provided_bytes = provided.encode() if isinstance(provided, str) else provided
        return hmac.compare_digest(provided_bytes, self._api_key)


async def _abort(request: Any, context: grpc.aio.ServicerContext[Any, Any]) -> None:
    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing or invalid API key")


def _reject(handler: Any) -> grpc.RpcMethodHandler:
    """Обработчик того же типа (unary/stream), что и настоящий, но сразу отвечающий UNAUTHENTICATED."""
    kwargs = {
        "request_deserializer": handler.request_deserializer,
        "response_serializer": handler.response_serializer,
    }
    if handler.unary_unary:
        return grpc.unary_unary_rpc_method_handler(_abort, **kwargs)
    if handler.unary_stream:
        return grpc.unary_stream_rpc_method_handler(_abort, **kwargs)
    if handler.stream_unary:
        return grpc.stream_unary_rpc_method_handler(_abort, **kwargs)
    return grpc.stream_stream_rpc_method_handler(_abort, **kwargs)
