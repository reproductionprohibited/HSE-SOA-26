import uuid
from datetime import UTC, datetime

from flight.v1 import flight_service_pb2 as pb
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import Booking

CURRENCY = "RUB"


def format_money(minor_units: int) -> str:
    """Копейки -> строка с двумя знаками: 650000 -> "6500.00"."""
    return f"{minor_units // 100}.{minor_units % 100:02d}"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class FlightOut(BaseModel):
    id: uuid.UUID
    flight_number: str
    airline_code: str
    airline_name: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int
    available_seats: int
    price: str = Field(examples=["6500.00"])
    currency: str = Field(examples=["RUB"])
    status: str = Field(examples=["SCHEDULED"])

    @classmethod
    def from_pb(cls, flight: pb.Flight) -> "FlightOut":
        return cls(
            id=uuid.UUID(flight.id),
            flight_number=flight.flight_number,
            airline_code=flight.airline_code,
            airline_name=flight.airline_name,
            origin=flight.origin,
            destination=flight.destination,
            departure_time=flight.departure_time.ToDatetime(tzinfo=UTC),
            arrival_time=flight.arrival_time.ToDatetime(tzinfo=UTC),
            total_seats=flight.total_seats,
            available_seats=flight.available_seats,
            price=format_money(flight.price),
            currency=flight.currency,
            status=pb.FlightStatus.Name(flight.status).removeprefix("FLIGHT_STATUS_"),
        )


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: uuid.UUID
    flight_id: uuid.UUID
    passenger_name: str = Field(min_length=1, max_length=200)
    passenger_email: EmailStr
    seat_count: int = Field(ge=1, le=10)


class BookingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    flight_id: uuid.UUID
    passenger_name: str
    passenger_email: str
    seat_count: int
    total_price: str = Field(examples=["13000.00"])
    currency: str = Field(examples=["RUB"])
    status: str = Field(examples=["CONFIRMED"])
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, booking: Booking) -> "BookingOut":
        return cls(
            id=booking.id,
            user_id=booking.user_id,
            flight_id=booking.flight_id,
            passenger_name=booking.passenger_name,
            passenger_email=booking.passenger_email,
            seat_count=booking.seat_count,
            total_price=format_money(booking.total_price),
            currency=CURRENCY,
            status=booking.status.value,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )
