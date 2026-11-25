from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_user: str = "analytics"
    clickhouse_password: str = "analytics"
    clickhouse_db: str = "analytics"

    postgres_dsn: str = "postgresql://analytics:analytics@postgres:5432/analytics"
    postgres_max_attempts: int = 5
    postgres_backoff_max_s: float = 10.0

    # Интервал планового пересчёта
    agg_interval_seconds: int = 60
    # Каждый цикл пересчитывает «сегодня» и N предыдущих дней: поздние события, новые точки retention
    # и история, загруженная до запуска сервиса. Один день — доли секунды, поэтому окно дешёвое.
    agg_lookback_days: int = 14
    # Сколько фильмов рейтинга выгружать в PostgreSQL
    top_n: int = 10


settings = Settings()
