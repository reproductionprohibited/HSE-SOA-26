"""gRPC-слой: валидация и маппинг proto ↔ домен, доменные ошибки -> status codes."""

import functools
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any, cast

import grpc
from flight.v1 import flight_service_pb2 as pb
from flight.v1 import flight_service_pb2_grpc as pb_grpc

from app.cache.flight_cache import FlightCache
from app.db.session import SessionFactory
from app.domain import errors
from app.mappers import FLIGHT_STATUS_FROM_PB, reservation_to_pb
from app.services import flights, reservations
from app.services.flights import FlightChanges

logger = logging.getLogger(__name__)

IATA_RE = re.compile(r"^[A-Z]{3}$")
UPDATABLE_FIELDS = frozenset({"price", "status", "departure_time", "arrival_time"})

_ERROR_CODES: dict[type[errors.DomainError], grpc.StatusCode] = {
    errors.InvalidArgument: grpc.StatusCode.INVALID_ARGUMENT,
    errors.FlightNotFound: grpc.StatusCode.NOT_FOUND,
    errors.ReservationNotFound: grpc.StatusCode.NOT_FOUND,
    errors.FlightNotAvailable: grpc.StatusCode.FAILED_PRECONDITION,
    errors.NotEnoughSeats: grpc.StatusCode.RESOURCE_EXHAUSTED,
    errors.ReservationAlreadyExists: grpc.StatusCode.ALREADY_EXISTS,
    errors.FlightAlreadyExists: grpc.StatusCode.ALREADY_EXISTS,
    errors.InjectedResponseLoss: grpc.StatusCode.UNAVAILABLE,
}


def rpc[F: Callable[..., Awaitable[Any]]](method: F) -> F:
    """Логирует вызов и превращает исключения в gRPC status. Сигнатура метода сохраняется."""

    @functools.wraps(method)
    async def wrapper(self: "FlightServicer", request: Any, context: grpc.aio.ServicerContext[Any, Any]) -> Any:
        started = time.perf_counter()
        code, message = grpc.StatusCode.OK, ""
        try:
            return await method(self, request, context)
        except errors.DomainError as exc:
            code, message = _ERROR_CODES[type(exc)], str(exc)
        except Exception:
            logger.exception("unhandled error", extra={"fields": {"method": method.__name__}})
            code, message = grpc.StatusCode.INTERNAL, "internal error"
        finally:
            logger.info(
                "rpc handled",
                extra={
                    "fields": {
                        "method": method.__name__,
                        "code": code.name,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        **({"error": message} if message else {}),
                    }
                },
            )
        await context.abort(code, message)

    return cast(F, wrapper)


class FlightServicer(pb_grpc.FlightServiceServicer):
    def __init__(self, cache: FlightCache, drop_reserve_responses: int = 0) -> None:
        self._cache = cache
        self._drop_reserve_responses = drop_reserve_responses

    @rpc
    async def SearchFlights(self, request: pb.SearchFlightsRequest, context) -> pb.SearchFlightsResponse:
        origin = _parse_iata(request.origin, "origin")
        destination = _parse_iata(request.destination, "destination")
        departure_date = _parse_date(request.date) if request.HasField("date") else None
        async with SessionFactory() as session:
            return await flights.search_flights(session, self._cache, origin, destination, departure_date)

    @rpc
    async def GetFlight(self, request: pb.GetFlightRequest, context) -> pb.Flight:
        flight_id = _parse_uuid(request.flight_id, "flight_id")
        async with SessionFactory() as session:
            return await flights.get_flight(session, self._cache, flight_id)

    @rpc
    async def ReserveSeats(self, request: pb.ReserveSeatsRequest, context) -> pb.SeatReservation:
        flight_id = _parse_uuid(request.flight_id, "flight_id")
        booking_id = _parse_uuid(request.booking_id, "booking_id")
        if request.seat_count <= 0:
            raise errors.InvalidArgument("seat_count must be positive")
        async with SessionFactory() as session:
            reservation = await reservations.reserve_seats(
                session, self._cache, flight_id, request.seat_count, booking_id
            )
        if self._drop_reserve_responses > 0:
            # Резервация уже закоммичена — клиент видит сбой и повторяет запрос
            self._drop_reserve_responses -= 1
            raise errors.InjectedResponseLoss()
        return reservation_to_pb(reservation)

    @rpc
    async def ReleaseReservation(self, request: pb.ReleaseReservationRequest, context) -> pb.SeatReservation:
        booking_id = _parse_uuid(request.booking_id, "booking_id")
        async with SessionFactory() as session:
            reservation = await reservations.release_reservation(session, self._cache, booking_id)
        return reservation_to_pb(reservation)

    @rpc
    async def UpdateFlight(self, request: pb.UpdateFlightRequest, context) -> pb.Flight:
        flight_id = _parse_uuid(request.flight.id, "flight.id")
        changes = _parse_flight_changes(request)
        async with SessionFactory() as session:
            return await flights.update_flight(session, self._cache, flight_id, changes)


def _parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise errors.InvalidArgument(f"{field} must be a valid UUID") from None


def _parse_iata(value: str, field: str) -> str:
    if not IATA_RE.match(value):
        raise errors.InvalidArgument(f"{field} must be an IATA code of 3 uppercase letters")
    return value


def _parse_date(value: pb.Date) -> date:
    try:
        return date(value.year, value.month, value.day)
    except ValueError:
        raise errors.InvalidArgument("date is not a valid calendar date") from None


def _parse_flight_changes(request: pb.UpdateFlightRequest) -> FlightChanges:
    paths = set(request.update_mask.paths)
    if not paths:
        raise errors.InvalidArgument("update_mask must list at least one field")
    if unknown := paths - UPDATABLE_FIELDS:
        raise errors.InvalidArgument(
            f"fields {sorted(unknown)} cannot be updated, allowed: {sorted(UPDATABLE_FIELDS)}"
        )

    flight = request.flight
    price = status = departure_time = arrival_time = None
    if "price" in paths:
        if flight.price <= 0:
            raise errors.InvalidArgument("price must be positive")
        price = flight.price
    if "status" in paths:
        if flight.status not in FLIGHT_STATUS_FROM_PB:
            raise errors.InvalidArgument("status must be specified")
        status = FLIGHT_STATUS_FROM_PB[flight.status]
    if "departure_time" in paths:
        departure_time = _parse_timestamp(flight, "departure_time")
    if "arrival_time" in paths:
        arrival_time = _parse_timestamp(flight, "arrival_time")
    return FlightChanges(price=price, status=status, departure_time=departure_time, arrival_time=arrival_time)


def _parse_timestamp(flight: pb.Flight, field: str) -> datetime:
    if not flight.HasField(field):
        raise errors.InvalidArgument(f"{field} is in update_mask but not set")
    return getattr(flight, field).ToDatetime(tzinfo=UTC)
