import logging
import uuid
from datetime import UTC, datetime

import grpc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Booking, BookingStatus
from app.errors import BookingNotCancellable, BookingNotFound
from app.flight_client.circuit_breaker import CircuitOpenError
from app.flight_client.client import FlightClient

logger = logging.getLogger(__name__)

# Коды, при которых неизвестно, выполнился ли вызов на стороне Flight Service
_OUTCOME_UNKNOWN = frozenset({grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED})


async def create_booking(
    session: AsyncSession,
    flight_client: FlightClient,
    *,
    user_id: uuid.UUID,
    flight_id: uuid.UUID,
    passenger_name: str,
    passenger_email: str,
    seat_count: int,
) -> Booking:
    # ID бронирования известен до резервации — он же booking_id резервации во Flight Service
    booking_id = uuid.uuid4()

    flight = await flight_client.get_flight(flight_id)

    # Ошибка резервации (нет мест, рейс не SCHEDULED, ...) пробрасывается — бронирование не создаётся
    try:
        await flight_client.reserve_seats(flight_id, seat_count, booking_id)
    except grpc.aio.AioRpcError as exc:
        if exc.code() in _OUTCOME_UNKNOWN:
            # Резервация могла выполниться на сервере, а ответ потеряться — места не должны «утечь»
            await _compensate_reservation(flight_client, booking_id, reason=f"ReserveSeats {exc.code().name}")
        raise

    booking = Booking(
        id=booking_id,
        user_id=user_id,
        flight_id=flight_id,
        passenger_name=passenger_name,
        passenger_email=passenger_email,
        seat_count=seat_count,
        total_price=seat_count * flight.price,  # snapshot цены на момент бронирования
        status=BookingStatus.CONFIRMED,
    )
    try:
        async with session.begin():
            session.add(booking)
            if settings.fault_fail_booking_insert:
                raise RuntimeError("fault injection: booking insert failed")
    except Exception:
        # Места зарезервированы, а бронирования нет — возвращаем места
        await _compensate_reservation(flight_client, booking_id, reason="booking insert failed")
        raise

    logger.info(
        "booking created",
        extra={"fields": {"booking_id": booking_id, "flight_id": flight_id, "seat_count": seat_count}},
    )
    return booking


async def _compensate_reservation(flight_client: FlightClient, booking_id: uuid.UUID, *, reason: str) -> None:
    """Best-effort отмена резервации созданного не до конца бронирования. Ошибки не пробрасываются."""
    fields: dict[str, object] = {"booking_id": booking_id, "reason": reason}
    try:
        await flight_client.release_reservation(booking_id)
    except grpc.aio.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            # Резервация не создавалась — возвращать нечего
            logger.info("compensation not needed: no reservation", extra={"fields": fields})
            return
        logger.error(
            "compensation failed: seats may stay reserved",
            extra={"fields": {**fields, "grpc_code": exc.code().name, "grpc_details": exc.details()}},
        )
        return
    except CircuitOpenError:
        logger.error("compensation failed: seats may stay reserved", extra={"fields": {**fields, "error": "circuit open"}})
        return
    logger.warning("reservation compensated", extra={"fields": fields})


async def get_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFound(booking_id)
    return booking


async def list_bookings(session: AsyncSession, user_id: uuid.UUID) -> list[Booking]:
    stmt = select(Booking).where(Booking.user_id == user_id).order_by(Booking.created_at.desc())
    return list((await session.scalars(stmt)).all())


async def cancel_booking(session: AsyncSession, flight_client: FlightClient, booking_id: uuid.UUID) -> Booking:
    async with session.begin():
        # Блокировка строки: параллельные отмены одного бронирования выполняются по очереди
        booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
        if booking is None:
            raise BookingNotFound(booking_id)
        if booking.status != BookingStatus.CONFIRMED:
            raise BookingNotCancellable(booking_id, booking.status.value)

        # Ошибка возврата мест -> откат транзакции, бронирование остаётся CONFIRMED
        await flight_client.release_reservation(booking_id)

        booking.status = BookingStatus.CANCELLED
        booking.updated_at = datetime.now(UTC)

    logger.info("booking cancelled", extra={"fields": {"booking_id": booking_id}})
    return booking
