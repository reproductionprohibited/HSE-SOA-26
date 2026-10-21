"""Логирование каждого API-запроса.

Чистый ASGI-middleware, которым обёрнуто всё FastAPI-приложение снаружи:
видит финальный статус любого ответа (включая 500 из обработчика ошибок)
и добавляет X-Request-Id во все ответы.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import request_id_var

logger = logging.getLogger("app.access")

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "secret", "authorization"}
MASK = "***"
MAX_LOGGED_BODY = 10_000


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: MASK if k.lower() in SENSITIVE_KEYS else mask_sensitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(v) for v in value]
    return value


def _body_for_log(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return mask_sensitive(json.loads(raw))
    except ValueError:
        # Не JSON (например, битое тело) — пишем как есть, с ограничением размера
        return raw[:MAX_LOGGED_BODY].decode("utf-8", errors="replace")


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        method = scope["method"]
        status_code = 500
        # request.state внутри приложения пишет в этот же dict: зависимость authenticate
        # кладёт сюда user_id из проверенного access token
        state = scope.setdefault("state", {})

        # Тело мутирующего запроса читаем целиком заранее и отдаём приложению из буфера,
        # чтобы залогировать его даже если приложение тело не читало (404, 405)
        body = b""
        app_receive = receive
        if method in MUTATING_METHODS:
            more_body = True
            while more_body:
                message = await receive()
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            body_sent = False

            async def app_receive() -> Message:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append("X-Request-Id", request_id)
            await send(message)

        try:
            await self.app(scope, app_receive, send_with_request_id)
        except Exception:
            # Ответ 500 уже отправлен обработчиком ошибок, стектрейс залогирован там же
            pass
        finally:
            fields = {
                "request_id": request_id,
                "method": method,
                "endpoint": scope["path"],
                "query": scope["query_string"].decode() or None,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "user_id": state.get("user_id"),
                "timestamp": started_at.isoformat(timespec="milliseconds"),
            }
            if method in MUTATING_METHODS:
                fields["request_body"] = _body_for_log(body)
            level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
            logger.log(level, f"{method} {scope['path']} -> {status_code}", extra={"fields": fields})
            request_id_var.reset(token)
