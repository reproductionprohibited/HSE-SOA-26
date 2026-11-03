"""Маппинг ORM-моделей ↔ protobuf-сообщения."""

from datetime import UTC

from flight.v1 import flight_service_pb2 as pb

from app.db.models import Flight, FlightStatus, ReservationStatus, SeatReservation

CURRENCY = "RUB"

FLIGHT_STATUS_TO_PB = {
    FlightStatus.SCHEDULED: pb.FLIGHT_STATUS_SCHEDULED,
    FlightStatus.DEPARTED: pb.FLIGHT_STATUS_DEPARTED,
    FlightStatus.CANCELLED: pb.FLIGHT_STATUS_CANCELLED,
    FlightStatus.COMPLETED: pb.FLIGHT_STATUS_COMPLETED,
}
FLIGHT_STATUS_FROM_PB = {v: k for k, v in FLIGHT_STATUS_TO_PB.items()}

RESERVATION_STATUS_TO_PB = {
    ReservationStatus.ACTIVE: pb.RESERVATION_STATUS_ACTIVE,
    ReservationStatus.RELEASED: pb.RESERVATION_STATUS_RELEASED,
    ReservationStatus.EXPIRED: pb.RESERVATION_STATUS_EXPIRED,
}


def flight_to_pb(flight: Flight) -> pb.Flight:
    message = pb.Flight(
        id=str(flight.id),
        flight_number=flight.flight_number,
        airline_code=flight.airline_code,
        airline_name=flight.airline.name,
        origin=flight.origin,
        destination=flight.destination,
        total_seats=flight.total_seats,
        available_seats=flight.available_seats,
        price=flight.price,
        currency=CURRENCY,
        status=FLIGHT_STATUS_TO_PB[flight.status],
    )
    message.departure_time.FromDatetime(flight.departure_time.astimezone(UTC))
    message.arrival_time.FromDatetime(flight.arrival_time.astimezone(UTC))
    return message


def reservation_to_pb(reservation: SeatReservation) -> pb.SeatReservation:
    message = pb.SeatReservation(
        id=str(reservation.id),
        flight_id=str(reservation.flight_id),
        booking_id=str(reservation.booking_id),
        seat_count=reservation.seat_count,
        status=RESERVATION_STATUS_TO_PB[reservation.status],
    )
    message.created_at.FromDatetime(reservation.created_at.astimezone(UTC))
    message.updated_at.FromDatetime(reservation.updated_at.astimezone(UTC))
    return message
