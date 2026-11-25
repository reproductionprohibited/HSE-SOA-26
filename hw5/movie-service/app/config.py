from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "kafka:9092"
    schema_registry_url: str = "http://schema-registry:8081"
    topic: str = "movie-events"

    # Прикладной retry поверх ретраев librdkafka: срабатывает, когда delivery report вернул ошибку
    publish_max_attempts: int = 5
    publish_backoff_initial_s: float = 0.2
    publish_backoff_max_s: float = 5.0
    # Сколько librdkafka сам пытается доставить сообщение, прежде чем вернуть ошибку в delivery report
    delivery_timeout_ms: int = 15000

    # Генератор
    generator_seed: int = 42
    generator_backfill_days: int = 14
    generator_new_users_per_day: int = 60
    generator_movies: int = 120
    generator_eps: float = 5.0
    generator_concurrent_sessions: int = 20


settings = Settings()
