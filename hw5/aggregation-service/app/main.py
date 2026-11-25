import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query

from app.aggregator import Aggregator, CycleResult
from app.config import settings
from app.logging_config import setup_logging
from app.sink_postgres import PostgresSink

setup_logging()
log = logging.getLogger("aggregation-service")

aggregator = Aggregator(settings, PostgresSink(settings))
# Плановый и ручной пересчёт не выполняются одновременно
cycle_lock = asyncio.Lock()


async def run_cycle(day: date, trigger: Literal["schedule", "manual"]) -> CycleResult:
    async with cycle_lock:
        log.info("aggregation started", extra={"date": day.isoformat(), "trigger": trigger})
        started = time.monotonic()
        try:
            result = await asyncio.to_thread(aggregator.run, day)
        except Exception as exc:
            log.exception(
                "aggregation failed",
                extra={"date": day.isoformat(), "trigger": trigger, "error": str(exc),
                       "duration_ms": round((time.monotonic() - started) * 1000)},
            )
            raise
        log.info(
            "aggregation finished",
            extra={
                "date": day.isoformat(),
                "trigger": trigger,
                "events_processed": result.events_processed,
                "clickhouse_rows_written": sum(result.clickhouse_rows_written.values()),
                "postgres_rows_written": result.postgres_rows_written,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return result


async def scheduled_cycle() -> None:
    # Окно [сегодня - lookback, сегодня] в хронологическом порядке: retention когорты D опирается на
    # пересчёт следующих за D дней
    today = datetime.now(UTC).date()
    for n in range(settings.agg_lookback_days, -1, -1):
        try:
            await run_cycle(today - timedelta(days=n), "schedule")
        except Exception:
            pass  # уже залогировано; следующий цикл повторит попытку


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_cycle, "interval", seconds=settings.agg_interval_seconds,
        next_run_time=datetime.now(UTC), max_instances=1, coalesce=True, id="aggregation",
    )
    scheduler.start()
    log.info(
        "aggregation-service started",
        extra={"interval_s": settings.agg_interval_seconds, "lookback_days": settings.agg_lookback_days},
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Aggregation Service", lifespan=lifespan)


@app.post("/recompute")
async def recompute(day: date = Query(alias="date", description="YYYY-MM-DD")) -> dict:
    try:
        result = await run_cycle(day, "manual")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"aggregation failed: {exc}") from exc
    return asdict(result)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
