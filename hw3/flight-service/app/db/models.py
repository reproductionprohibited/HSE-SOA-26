"""ORM-модели. Схема создаётся миграциями Liquibase, здесь — только маппинг."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class FlightStatus(enum.StrEnum):
    SCHEDULED = "SCHEDULED"
    DEPARTED = "DEPARTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ReservationStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Airline(Base):
    __tablename__ = "airlines"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str]


class Airport(Base):
    __tablename__ = "airports"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str]
    city: Mapped[str]
    country: Mapped[str]


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    airline_code: Mapped[str] = mapped_column(ForeignKey("airlines.code"))
    flight_no: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.code"))
    destination: Mapped[str] = mapped_column(ForeignKey("airports.code"))
    departure_time: Mapped[datetime]
    arrival_time: Mapped[datetime]
    total_seats: Mapped[int]
    available_seats: Mapped[int]
    price: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[FlightStatus] = mapped_column(ENUM(FlightStatus, name="flight_status", create_type=False))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # many-to-one, грузится одним JOIN вместе с рейсом — нужен airline_name в ответе
    airline: Mapped[Airline] = relationship(lazy="joined")

    @property
    def flight_number(self) -> str:
        return f"{self.airline_code}{self.flight_no}"


class SeatReservation(Base):
    __tablename__ = "seat_reservations"
    # created_at/updated_at заполняет БД — забираем их через RETURNING сразу при INSERT
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flights.id"))
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    seat_count: Mapped[int]
    status: Mapped[ReservationStatus] = mapped_column(
        ENUM(ReservationStatus, name="reservation_status", create_type=False),
        server_default=ReservationStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
