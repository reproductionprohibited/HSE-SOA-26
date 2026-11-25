import logging
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from app.config import Settings
from app.metrics import QUERIES
from app.sink_postgres import TOP_MOVIES_METRIC, MetricRow, PostgresSink

log = logging.getLogger("aggregator")

# Retention пересчитывается для когорт [D-7, D], поэтому в PostgreSQL выгружаем скалярные метрики за то же окно
RETENTION_WINDOW_DAYS = 7


@dataclass
class CycleResult:
    date: date
    events_processed: int
    clickhouse_rows_written: dict[str, int] = field(default_factory=dict)
    postgres_rows_written: int = 0


class Aggregator:
    """Один цикл: агрегаты за дату считаются в ClickHouse (INSERT ... SELECT в витрины agg_*),
    затем готовые метрики выгружаются в PostgreSQL."""

    def __init__(self, settings: Settings, sink: PostgresSink) -> None:
        self._settings = settings
        self._sink = sink

    def _client(self) -> Client:
        s = self._settings
        return clickhouse_connect.get_client(
            host=s.clickhouse_host, port=s.clickhouse_port, username=s.clickhouse_user,
            password=s.clickhouse_password, database=s.clickhouse_db,
        )

    def run(self, day: date) -> CycleResult:
        ch = self._client()
        try:
            params = {"date": day}
            events = ch.query("SELECT count() FROM movie_events FINAL WHERE event_date = {date:Date}", parameters=params)
            result = CycleResult(date=day, events_processed=int(events.result_rows[0][0]))

            for name, sql in QUERIES:
                summary = ch.command(sql, parameters=params)
                result.clickhouse_rows_written[name] = int(getattr(summary, "written_rows", 0))

            rows = self._read_ready_metrics(ch, day)
        finally:
            ch.close()

        result.postgres_rows_written = self._sink.write(day, rows)
        return result

    def _read_ready_metrics(self, ch: Client, day: date) -> list[MetricRow]:
        params = {"from": day - timedelta(days=RETENTION_WINDOW_DAYS), "to": day, "date": day, "n": self._settings.top_n}
        daily = ch.query(
            """
            SELECT metric_date, metric_name, value, computed_at
            FROM agg_daily_metrics FINAL
            WHERE metric_date BETWEEN {from:Date} AND {to:Date}
            """,
            parameters=params,
        )
        top = ch.query(
            """
            SELECT movie_id, views, computed_at
            FROM agg_top_movies FINAL
            WHERE metric_date = {date:Date}
            ORDER BY rank
            LIMIT {n:UInt32}
            """,
            parameters=params,
        )
        rows = [
            MetricRow(metric_date=d, metric_name=name, dimension="", value=value, computed_at=ts.replace(tzinfo=UTC))
            for d, name, value, ts in daily.result_rows
        ]
        rows += [
            MetricRow(metric_date=day, metric_name=TOP_MOVIES_METRIC, dimension=movie_id, value=float(views),
                      computed_at=ts.replace(tzinfo=UTC))
            for movie_id, views, ts in top.result_rows
        ]
        return rows
