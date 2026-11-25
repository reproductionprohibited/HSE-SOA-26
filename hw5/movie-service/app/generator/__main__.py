"""Генератор синтетических событий: python -m app.generator

1. Backfill: события за последние GENERATOR_BACKFILL_DAYS полных дней — без них retention и когорты пустые.
2. Realtime: поток событий «сегодняшних» пользователей с частотой GENERATOR_EPS.
"""

import asyncio
import logging
import random
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.config import settings
from app.generator.model import active_users, day_events, make_movies, session_events
from app.logging_config import setup_logging
from app.producer import EventPublisher, PublishError
from app.schemas import MovieEvent

HEARTBEAT = Path("/tmp/generator-heartbeat")

log = logging.getLogger("generator")


def backfill(publisher: EventPublisher, today: date) -> None:
    movies, weights = make_movies(settings.generator_seed, settings.generator_movies)
    first_cohort = today - timedelta(days=settings.generator_backfill_days)
    total = 0
    for offset in range(settings.generator_backfill_days, 0, -1):
        day = today - timedelta(days=offset)
        events = day_events(
            settings.generator_seed, day, first_cohort, settings.generator_new_users_per_day, movies, weights
        )
        for event in events:
            publisher.publish_nowait(event)
        publisher.flush()
        total += len(events)
        log.info("backfill day done", extra={"day": day.isoformat(), "events": len(events)})
        HEARTBEAT.touch()
    log.info("backfill finished", extra={"days": settings.generator_backfill_days, "events": total})


async def realtime(publisher: EventPublisher) -> None:
    movies, weights = make_movies(settings.generator_seed, settings.generator_movies)
    rng = random.Random()
    sessions: list[list[MovieEvent]] = []
    interval = 1 / settings.generator_eps
    users_day, users = None, []
    log.info("realtime started", extra={"eps": settings.generator_eps})

    while True:
        started = time.monotonic()
        today = datetime.now(UTC).date()
        if users_day != today:
            first_cohort = today - timedelta(days=settings.generator_backfill_days)
            users_day = today
            users = active_users(settings.generator_seed, today, first_cohort, settings.generator_new_users_per_day)

        while len(sessions) < settings.generator_concurrent_sessions:
            # rng без seed: event_id и session_id в realtime случайные, детерминизм нужен только backfill
            sessions.append(session_events(rng, rng.choice(users), movies, weights, datetime.now(UTC)))

        # Следующее событие случайной сессии; время — момент отправки, порядок внутри сессии сохраняется
        session = rng.choice(sessions)
        event = session.pop(0).model_copy(update={"timestamp": datetime.now(UTC)})
        if not session:
            sessions.remove(session)

        try:
            await publisher.publish(event)
        except PublishError:
            pass  # уже залогировано продюсером; генератор продолжает работу
        HEARTBEAT.touch()
        await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))


async def main() -> None:
    setup_logging()
    publisher = EventPublisher(settings)
    try:
        await asyncio.to_thread(backfill, publisher, datetime.now(UTC).date())
        await realtime(publisher)
    finally:
        publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
