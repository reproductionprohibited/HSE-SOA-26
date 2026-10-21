from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from sqlalchemy import text

from app.auth.dependencies import authenticate
from app.config import settings
from app.db.session import engine
from app.errors import register_error_handlers
from app.handlers import MarketplaceApiImpl
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware
from marketplace_api.api import create_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Падаем на старте, если БД недоступна
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Marketplace API", version="1.0.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(create_router(MarketplaceApiImpl(), authenticate))

    # /openapi.json и /docs должны показывать написанный openapi, а не то что FastAPI
    # сгенерирует автоматически
    spec = yaml.safe_load(Path(settings.openapi_spec_path).read_text(encoding="utf-8"))
    app.openapi = lambda: spec
    return app


setup_logging(settings.log_level)

# Middleware логирования оборачивает приложение целиком (снаружи обработчика 500),
# поэтому видит итоговый статус любого ответа
app = RequestLoggingMiddleware(create_app())
