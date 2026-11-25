from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventType(StrEnum):
    VIEW_STARTED = "VIEW_STARTED"
    VIEW_FINISHED = "VIEW_FINISHED"
    VIEW_PAUSED = "VIEW_PAUSED"
    VIEW_RESUMED = "VIEW_RESUMED"
    LIKED = "LIKED"
    SEARCHED = "SEARCHED"

    @property
    def is_view(self) -> bool:
        return self.name.startswith("VIEW_")


class DeviceType(StrEnum):
    MOBILE = "MOBILE"
    DESKTOP = "DESKTOP"
    TV = "TV"
    TABLET = "TABLET"


class MovieEvent(BaseModel):
    """Событие в терминах Avro-схемы schemas/movie_event.avsc (первый слой валидации)."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(min_length=1)
    movie_id: str = Field(min_length=1)
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    device_type: DeviceType
    session_id: str = Field(min_length=1)
    progress_seconds: int | None = Field(default=None, ge=0, le=2**31 - 1)

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        # Время без зоны считаем UTC, с зоной — переводим в UTC
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)

    @model_validator(mode="after")
    def _progress_only_for_views(self) -> "MovieEvent":
        if self.event_type.is_view and self.progress_seconds is None:
            raise ValueError(f"progress_seconds is required for {self.event_type}")
        if not self.event_type.is_view and self.progress_seconds is not None:
            raise ValueError(f"progress_seconds must be null for {self.event_type}")
        return self

    def to_avro(self) -> dict[str, Any]:
        """Словарь для AvroSerializer: uuid → str, enum → имя символа, datetime → timestamp-millis."""
        return {
            "event_id": str(self.event_id),
            "user_id": self.user_id,
            "movie_id": self.movie_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "device_type": self.device_type.value,
            "session_id": self.session_id,
            "progress_seconds": self.progress_seconds,
        }


class PublishedResponse(BaseModel):
    event_id: UUID
    partition: int
    offset: int
