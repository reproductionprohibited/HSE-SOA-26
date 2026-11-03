import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import BookingCreate, BookingOut, ErrorResponse, FlightOut
from app.db.session import get_session
from app.flight_client.client import FlightClient
from app.services import bookings

IATA_PATTERN = r"^[A-Z]{3}$"


def get_flight_client(request: Request) -> FlightClient:
    return request.app.state.flight_client


SessionDep = Annotated[AsyncSession, Depends(get_session)]
FlightClientDep = Annotated[FlightClient, Depends(get_flight_client)]

_errors: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 404, 409, 502, 503, 504)
}

flights_router = APIRouter(prefix="/flights", tags=["flights"], responses=_errors)
bookings_router = APIRouter(prefix="/bookings", tags=["bookings"], responses=_errors)


@flights_router.get("", response_model=list[FlightOut])
async def search_flights(
    flight_client: FlightClientDep,
    origin: Annotated[str, Query(pattern=IATA_PATTERN, examples=["SVO"])],
    destination: Annotated[str, Query(pattern=IATA_PATTERN, examples=["LED"])],
    date: Annotated[date | None, Query(examples=["2026-12-01"])] = None,
) -> list[FlightOut]:
    found = await flight_client.search_flights(origin, destination, date)
    return [FlightOut.from_pb(f) for f in found]


@flights_router.get("/{flight_id}", response_model=FlightOut)
async def get_flight(flight_id: uuid.UUID, flight_client: FlightClientDep) -> FlightOut:
    return FlightOut.from_pb(await flight_client.get_flight(flight_id))


@bookings_router.post("", response_model=BookingOut, status_code=201)
async def create_booking(body: BookingCreate, session: SessionDep, flight_client: FlightClientDep) -> BookingOut:
    booking = await bookings.create_booking(
        session,
        flight_client,
        user_id=body.user_id,
        flight_id=body.flight_id,
        passenger_name=body.passenger_name,
        passenger_email=str(body.passenger_email),
        seat_count=body.seat_count,
    )
    return BookingOut.from_model(booking)


@bookings_router.get("", response_model=list[BookingOut])
async def list_bookings(user_id: uuid.UUID, session: SessionDep) -> list[BookingOut]:
    return [BookingOut.from_model(b) for b in await bookings.list_bookings(session, user_id)]


@bookings_router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: uuid.UUID, session: SessionDep) -> BookingOut:
    return BookingOut.from_model(await bookings.get_booking(session, booking_id))


@bookings_router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(booking_id: uuid.UUID, session: SessionDep, flight_client: FlightClientDep) -> BookingOut:
    return BookingOut.from_model(await bookings.cancel_booking(session, flight_client, booking_id))
