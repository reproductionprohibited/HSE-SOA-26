import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.logging_config import setup_logging
from app.producer import EventPublisher, EventValidationError, PublishError
from app.schemas import MovieEvent, PublishedResponse

setup_logging()
log = logging.getLogger("movie-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.publisher = EventPublisher(settings)
    log.info("movie-service started", extra={"bootstrap": settings.kafka_bootstrap_servers, "topic": settings.topic})
    yield
    await asyncio.to_thread(app.state.publisher.close)


app = FastAPI(title="Movie Service", lifespan=lifespan)


@app.post("/events", status_code=status.HTTP_202_ACCEPTED, response_model=PublishedResponse)
async def publish_event(event: MovieEvent) -> PublishedResponse:
    publisher: EventPublisher = app.state.publisher
    try:
        msg = await publisher.publish(event)
    except EventValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"avro validation failed: {exc}") from exc
    except PublishError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"kafka unavailable: {exc}") from exc
    except Exception as exc:  # Schema Registry недоступен и т.п.
        log.exception("publish failed unexpectedly", extra={"event_id": str(event.event_id)})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return PublishedResponse(event_id=event.event_id, partition=msg.partition() or 0, offset=msg.offset() or 0)


@app.get("/health")
async def health() -> JSONResponse:
    try:
        await asyncio.to_thread(app.state.publisher.check_connection)
    except Exception as exc:
        return JSONResponse({"status": "unavailable", "kafka": str(exc)}, status_code=503)
    return JSONResponse({"status": "ok"})
