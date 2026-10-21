from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://marketplace:marketplace@localhost:5432/marketplace"

    # N минут между операциями CREATE_ORDER / UPDATE_ORDER одного пользователя
    order_rate_limit_minutes: int = 5

    openapi_spec_path: str = "openapi/marketplace.yaml"

    log_level: str = "INFO"

    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7


settings = Settings()
