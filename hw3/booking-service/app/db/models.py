"""ORM-модели. Схема создаётся миграциями Liquibase, здесь — только маппинг."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BookingStatus(enum.StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Booking(Base):
    __tablename__ = "bookings"
    # created_at/updated_at заполняет БД — забираем их через RETURNING сразу при INSERT
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    flight_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    passenger_name: Mapped[str]
    passenger_email: Mapped[str]
    seat_count: Mapped[int]
    total_price: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[BookingStatus] = mapped_column(ENUM(BookingStatus, name="booking_status", create_type=False))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
