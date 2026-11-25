"""Модель поведения пользователей. Детерминирована: одна и та же дата + seed дают те же события
(включая event_id), поэтому повторный backfill после рестарта генератора схлопывается в ClickHouse
(ReplacingMergeTree по event_id), а не раздувает метрики.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.schemas import DeviceType, EventType, MovieEvent

DEVICES = list(DeviceType)
DEVICE_WEIGHTS = [0.45, 0.25, 0.2, 0.1]

# Вероятность, что пользователь вернётся на n-й день после первого просмотра (n = 1..14)
RETURN_PROB = {n: 0.45 * 0.85 ** (n - 1) for n in range(1, 15)}

P_SEARCH_FIRST = 0.3
P_FINISH = 0.65
P_LIKE_AFTER_FINISH = 0.35
MAX_PAUSES = 3


@dataclass(frozen=True)
class Movie:
    movie_id: str
    duration_s: int


@dataclass(frozen=True)
class User:
    user_id: str
    cohort: date
    device: DeviceType


def make_movies(seed: int, count: int) -> tuple[list[Movie], list[float]]:
    rng = random.Random(f"{seed}:movies")
    movies = [Movie(f"movie-{i:04d}", rng.randint(80, 180) * 60) for i in range(1, count + 1)]
    # Популярность по закону Ципфа: несколько хитов и длинный хвост
    weights = [1 / i for i in range(1, count + 1)]
    return movies, weights


def new_users(seed: int, day: date, count: int) -> list[User]:
    rng = random.Random(f"{seed}:users:{day.isoformat()}")
    return [
        User(f"user-{day:%Y%m%d}-{i:03d}", day, rng.choices(DEVICES, DEVICE_WEIGHTS)[0])
        for i in range(count)
    ]


def active_users(seed: int, day: date, first_cohort: date, new_per_day: int) -> list[User]:
    """Новые пользователи дня + вернувшиеся из когорт [max(first_cohort, day-14), day-1]."""
    users = new_users(seed, day, new_per_day)
    cohort = max(first_cohort, day - timedelta(days=14))
    while cohort < day:
        n = (day - cohort).days
        for user in new_users(seed, cohort, new_per_day):
            if random.Random(f"{seed}:return:{user.user_id}:{n}").random() < RETURN_PROB[n]:
                users.append(user)
        cohort += timedelta(days=1)
    return users


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def session_events(
    rng: random.Random, user: User, movies: list[Movie], weights: list[float], start: datetime
) -> list[MovieEvent]:
    """Одна сессия: SEARCHED? → VIEW_STARTED → (PAUSED → RESUMED)* → VIEW_FINISHED | обрыв → LIKED?

    progress_seconds монотонно растёт и не превышает длительность фильма; VIEW_FINISHED всегда после
    VIEW_STARTED той же сессии.
    """
    movie = rng.choices(movies, weights)[0]
    device = user.device if rng.random() < 0.8 else rng.choice(DEVICES)
    session_id = str(_uuid(rng))
    now = start
    events: list[MovieEvent] = []

    def emit(event_type: EventType, progress: int | None) -> None:
        events.append(
            MovieEvent(
                event_id=_uuid(rng),
                user_id=user.user_id,
                movie_id=movie.movie_id,
                event_type=event_type,
                timestamp=now,
                device_type=device,
                session_id=session_id,
                progress_seconds=progress,
            )
        )

    if rng.random() < P_SEARCH_FIRST:
        emit(EventType.SEARCHED, None)
        now += timedelta(seconds=rng.randint(5, 90))

    progress = 0
    emit(EventType.VIEW_STARTED, progress)
    finishes = rng.random() < P_FINISH
    # Брошенный просмотр останавливается где-то посередине фильма
    stop_at = movie.duration_s if finishes else rng.randint(60, movie.duration_s - 60)

    for _ in range(rng.randint(0, MAX_PAUSES)):
        step = rng.randint(1, max(1, (stop_at - progress) // 2))
        if progress + step >= stop_at:
            break
        progress += step
        now += timedelta(seconds=step)
        emit(EventType.VIEW_PAUSED, progress)
        now += timedelta(seconds=rng.randint(10, 600))
        emit(EventType.VIEW_RESUMED, progress)

    now += timedelta(seconds=stop_at - progress)
    progress = stop_at
    if finishes:
        emit(EventType.VIEW_FINISHED, progress)
        if rng.random() < P_LIKE_AFTER_FINISH:
            now += timedelta(seconds=rng.randint(1, 30))
            emit(EventType.LIKED, None)
    else:
        emit(EventType.VIEW_PAUSED, progress)
    return events


def day_events(seed: int, day: date, first_cohort: date, new_per_day: int, movies: list[Movie], weights: list[float]) -> list[MovieEvent]:
    """Все события дня для backfill: у каждого активного пользователя 1–3 сессии в случайное время дня."""
    events: list[MovieEvent] = []
    day_start = datetime.combine(day, time(), UTC)
    for user in active_users(seed, day, first_cohort, new_per_day):
        rng = random.Random(f"{seed}:sessions:{user.user_id}:{day.isoformat()}")
        for _ in range(rng.choices([1, 2, 3], [0.6, 0.3, 0.1])[0]):
            # Сессия начинается не позже 18:00, чтобы с запасом закончиться в тот же день
            start = day_start + timedelta(seconds=rng.randint(0, 18 * 3600))
            events.extend(session_events(rng, user, movies, weights, start))
    events.sort(key=lambda e: e.timestamp)
    return events
