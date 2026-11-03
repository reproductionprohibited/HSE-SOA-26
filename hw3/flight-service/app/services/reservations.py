import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.flight_cache import FlightCache
from app.db.models import Flight, FlightStatus, ReservationStatus, SeatReservation
from app.domain.errors import (
    FlightNotAvailable,
    FlightNotFound,
    NotEnoughSeats,
    ReservationAlreadyExists,
    ReservationNotFound,
)

logger = logging.getLogger(__name__)


async def _lock_flight(session: AsyncSession, flight_id: uuid.UUID) -> Flight | None:
    # SELECT ... FOR UPDATE OF flights: конкурентные изменения одного рейса выполняются по очереди.
    # OF flights — чтобы не блокировать присоединённую (lazy="joined") строку airlines.
    return await session.scalar(select(Flight).where(Flight.id == flight_id).with_for_update(of=Flight))


async def reserve_seats(
    session: AsyncSession, cache: FlightCache, flight_id: uuid.UUID, seat_count: int, booking_id: uuid.UUID
) -> SeatReservation:
    """Списание мест и создание резервации — в одной транзакции под блокировкой строки рейса.

    Идемпотентен по booking_id: повтор с теми же параметрами возвращает существующую резервацию.
    """
    try:
        async with session.begin():
            flight = await _lock_flight(session, flight_id)
            if flight is None:
                raise FlightNotFound(flight_id)

            # Проверяем до остатка мест: повтор должен пройти, даже если места уже кончились
            existing = await session.scalar(select(SeatReservation).where(SeatReservation.booking_id == booking_id))
            if existing is not None:
                return _replay(existing, flight_id, seat_count)

            if flight.status != FlightStatus.SCHEDULED:
                raise FlightNotAvailable(flight_id, flight.status.value)
            # Проверка под блокировкой: два запроса за последнее место не пройдут её оба
            if flight.available_seats < seat_count:
                raise NotEnoughSeats(flight_id, seat_count, flight.available_seats)

            flight.available_seats -= seat_count
            flight.updated_at = datetime.now(UTC)
            reservation = SeatReservation(flight_id=flight_id, booking_id=booking_id, seat_count=seat_count)
            session.add(reservation)
            await session.flush()
    except IntegrityError as exc:
        # Конкурентный повтор с тем же booking_id на другой рейс (рейсы блокируются раздельно).
        # Транзакция откатилась целиком — места не списаны.
        if "seat_reservations_booking_id_uq" in str(exc.orig):
            raise ReservationAlreadyExists(booking_id) from exc
        raise

    # После COMMIT — см. FlightCache.invalidate_flight
    await cache.invalidate_flight(flight.id, flight.origin, flight.destination, flight.departure_time)
    logger.info(
        "seats reserved",
        extra={"fields": {"flight_id": flight_id, "booking_id": booking_id, "seat_count": seat_count}},
    )
    return reservation


def _replay(existing: SeatReservation, flight_id: uuid.UUID, seat_count: int) -> SeatReservation:
    if existing.flight_id != flight_id or existing.seat_count != seat_count:
        raise ReservationAlreadyExists(existing.booking_id)
    logger.info(
        "idempotent replay: reservation already exists",
        extra={"fields": {"booking_id": existing.booking_id, "reservation_id": existing.id}},
    )
    return existing


async def release_reservation(session: AsyncSession, cache: FlightCache, booking_id: uuid.UUID) -> SeatReservation:
    """Возврат мест и смена статуса резервации — в одной транзакции. Идемпотентен."""
    async with session.begin():
        # Порядок блокировок фиксирован: резервация -> рейс
        reservation = await session.scalar(
            select(SeatReservation).where(SeatReservation.booking_id == booking_id).with_for_update()
        )
        if reservation is None:
            raise ReservationNotFound(booking_id)
        if reservation.status != ReservationStatus.ACTIVE:
            # Уже освобождена — повторный вызов ничего не меняет
            return reservation

        flight = await _lock_flight(session, reservation.flight_id)
        assert flight is not None  # FK seat_reservations.flight_id -> flights.id

        now = datetime.now(UTC)
        flight.available_seats += reservation.seat_count
        flight.updated_at = now
        reservation.status = ReservationStatus.RELEASED
        reservation.updated_at = now

    await cache.invalidate_flight(flight.id, flight.origin, flight.destination, flight.departure_time)
    logger.info(
        "reservation released",
        extra={"fields": {"booking_id": booking_id, "flight_id": flight.id, "seat_count": reservation.seat_count}},
    )
    return reservation
