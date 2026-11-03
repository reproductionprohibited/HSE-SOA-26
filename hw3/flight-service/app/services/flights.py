import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from flight.v1 import flight_service_pb2 as pb
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.flight_cache import FlightCache, flight_key, search_key
from app.db.models import Flight, FlightStatus
from app.domain.errors import FlightAlreadyExists, FlightNotFound, InvalidArgument
from app.mappers import flight_to_pb

logger = logging.getLogger(__name__)


async def search_flights(
    session: AsyncSession, cache: FlightCache, origin: str, destination: str, departure_date: date | None
) -> pb.SearchFlightsResponse:
    async def load() -> pb.SearchFlightsResponse:
        stmt = (
            select(Flight)
            .where(
                Flight.origin == origin,
                Flight.destination == destination,
                Flight.status == FlightStatus.SCHEDULED,
            )
            .order_by(Flight.departure_time)
        )
        if departure_date is not None:
            # Дата вылета — сутки по UTC
            day_start = datetime.combine(departure_date, time.min, tzinfo=UTC)
            stmt = stmt.where(
                Flight.departure_time >= day_start,
                Flight.departure_time < day_start + timedelta(days=1),
            )
        found = (await session.scalars(stmt)).all()
        return pb.SearchFlightsResponse(flights=[flight_to_pb(f) for f in found])

    key = search_key(origin, destination, departure_date)
    return await cache.get_or_load(key, cache.search_ttl, pb.SearchFlightsResponse, load)


async def get_flight(session: AsyncSession, cache: FlightCache, flight_id: uuid.UUID) -> pb.Flight:
    async def load() -> pb.Flight:
        flight = await session.get(Flight, flight_id)
        if flight is None:
            raise FlightNotFound(flight_id)
        return flight_to_pb(flight)

    return await cache.get_or_load(flight_key(flight_id), cache.flight_ttl, pb.Flight, load)


@dataclass(frozen=True, kw_only=True)
class FlightChanges:
    """Изменяемые поля рейса; None — поле не меняется."""

    price: int | None = None
    status: FlightStatus | None = None
    departure_time: datetime | None = None
    arrival_time: datetime | None = None


async def update_flight(
    session: AsyncSession, cache: FlightCache, flight_id: uuid.UUID, changes: FlightChanges
) -> pb.Flight:
    async with session.begin():
        flight = await session.scalar(
            # OF flights — блокируем только рейс, а не присоединённую строку airlines
            select(Flight).where(Flight.id == flight_id).with_for_update(of=Flight)
        )
        if flight is None:
            raise FlightNotFound(flight_id)
        old_departure = flight.departure_time
        # После неудачного flush объект недоступен (транзакция откачена) — номер для ошибки запоминаем заранее
        flight_number = flight.flight_number

        if changes.price is not None:
            flight.price = changes.price
        if changes.status is not None:
            flight.status = changes.status
        if changes.departure_time is not None:
            flight.departure_time = changes.departure_time
        if changes.arrival_time is not None:
            flight.arrival_time = changes.arrival_time
        flight.updated_at = datetime.now(UTC)
        try:
            await session.flush()
        except IntegrityError as exc:
            # Исключение внутри session.begin() — транзакция откатывается
            constraint = _constraint_name(exc)
            if constraint == "flights_number_departure_date_uq":
                raise FlightAlreadyExists(flight_number) from exc
            raise InvalidArgument(f"update violates constraint {constraint}") from exc

    # После COMMIT: иначе конкурентный читатель успел бы закешировать старое значение из БД.
    # Дата вылета могла измениться — сбрасываем поиск и по старой, и по новой дате.
    await cache.invalidate_flight(flight.id, flight.origin, flight.destination, old_departure, flight.departure_time)
    logger.info("flight updated", extra={"fields": {"flight_id": flight_id}})
    return flight_to_pb(flight)


def _constraint_name(exc: IntegrityError) -> str | None:
    # asyncpg-исключение лежит в __cause__ у DBAPI-обёртки SQLAlchemy
    return getattr(exc.orig.__cause__, "constraint_name", None) if exc.orig else None
