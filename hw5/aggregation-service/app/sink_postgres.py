import logging
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from app.config import Settings

log = logging.getLogger("sink.postgres")

TOP_MOVIES_METRIC = "top_movie_views"

UPSERT = """
INSERT INTO daily_metrics (metric_date, metric_name, dimension, value, computed_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (metric_date, metric_name, dimension)
DO UPDATE SET value = EXCLUDED.value, computed_at = EXCLUDED.computed_at
"""

# Фильмы, выпавшие из top-N при пересчёте, удаляем в той же транзакции
DELETE_STALE_TOP = """
DELETE FROM daily_metrics
WHERE metric_date = %s AND metric_name = %s AND NOT (dimension = ANY(%s))
"""


@dataclass(frozen=True)
class MetricRow:
    metric_date: date
    metric_name: str
    dimension: str
    value: float
    computed_at: datetime


class PostgresSink:
    """Идемпотентная запись агрегатов: UPSERT по (metric_date, metric_name, dimension) в одной транзакции,
    retry с exponential backoff на ошибки соединения/записи."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def write(self, day: date, rows: list[MetricRow]) -> int:
        def before_sleep(state: RetryCallState) -> None:
            exc = state.outcome.exception() if state.outcome else None
            log.warning(
                "postgres write failed, retrying",
                extra={"date": day.isoformat(), "attempt": state.attempt_number,
                       "sleep_s": round(state.upcoming_sleep, 3), "error": str(exc)},
            )

        for attempt in Retrying(
            retry=retry_if_exception_type(psycopg.OperationalError),
            stop=stop_after_attempt(self._settings.postgres_max_attempts),
            wait=wait_random_exponential(multiplier=0.5, max=self._settings.postgres_backoff_max_s),
            before_sleep=before_sleep,
            reraise=True,
        ):
            with attempt:
                return self._write_once(day, rows)
        raise AssertionError("unreachable")

    def _write_once(self, day: date, rows: list[MetricRow]) -> int:
        top_ids = [r.dimension for r in rows if r.metric_name == TOP_MOVIES_METRIC and r.metric_date == day]
        with psycopg.connect(self._settings.postgres_dsn, connect_timeout=5) as conn, conn.transaction():
            with conn.cursor() as cur:
                cur.executemany(
                    UPSERT, [(r.metric_date, r.metric_name, r.dimension, r.value, r.computed_at) for r in rows]
                )
                cur.execute(DELETE_STALE_TOP, (day, TOP_MOVIES_METRIC, top_ids))
        return len(rows)
