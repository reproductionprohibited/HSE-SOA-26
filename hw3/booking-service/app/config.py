from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bookings:bookings@localhost:5432/bookings"

    flight_service_addr: str = "localhost:50051"
    # Deadline одного gRPC-вызова к Flight Service
    flight_service_timeout_seconds: float = 2.0

    flight_service_api_key: str = Field(min_length=1)

    retry_max_attempts: int = Field(default=3, ge=1)
    retry_initial_backoff_ms: int = Field(default=100, ge=0)

    # Circuit breaker: N сбоев за окно -> OPEN; через open_timeout -> HALF_OPEN
    cb_failure_threshold: int = Field(default=5, ge=1)
    cb_window_seconds: float = Field(default=30, gt=0)
    cb_open_timeout_seconds: float = Field(default=15, gt=0)

    log_level: str = "INFO"

    fault_fail_booking_insert: bool = False


settings = Settings()  # pyright: ignore[reportCallIssue]
