from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://flights:flights@localhost:5432/flights"
    grpc_port: int = 50051
    log_level: str = "INFO"

    # Обязателен: без ключа сервис не стартует
    flight_service_api_key: str = Field(min_length=1)

    # Адреса sentinel через запятую: host:port,host:port
    redis_sentinels: str = "localhost:26379"
    redis_master_name: str = "mymaster"
    # Короткий таймаут: недоступный Redis не должен тормозить запросы — идём в БД
    redis_timeout_seconds: float = 0.2
    cache_flight_ttl_seconds: int = Field(default=300, gt=0)
    cache_search_ttl_seconds: int = Field(default=300, gt=0)

    # Только для демо retry: первые N ответов ReserveSeats после старта теряются (UNAVAILABLE)
    fault_drop_reserve_responses: int = Field(default=0, ge=0)


    @property
    def redis_sentinel_addresses(self) -> list[tuple[str, int]]:
        hosts = (item.strip().rsplit(":", 1) for item in self.redis_sentinels.split(",") if item.strip())
        return [(host, int(port)) for host, port in hosts]


settings = Settings()  # pyright: ignore[reportCallIssue]
