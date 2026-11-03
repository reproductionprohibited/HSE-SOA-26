import asyncio
import logging
import signal

import grpc
from flight.v1 import flight_service_pb2 as pb
from flight.v1 import flight_service_pb2_grpc as pb_grpc
from grpc_reflection.v1alpha import reflection
from redis.asyncio.sentinel import Sentinel

from app.cache.flight_cache import FlightCache
from app.config import settings
from app.db.session import engine
from app.grpc_handlers import FlightServicer
from app.interceptors.auth import ApiKeyAuthInterceptor
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def serve() -> None:
    timeouts = {
        "socket_timeout": settings.redis_timeout_seconds,
        "socket_connect_timeout": settings.redis_timeout_seconds,
    }
    # Клиент спрашивает у sentinel адрес текущего мастера и сам переключается после failover
    sentinel = Sentinel(
        settings.redis_sentinel_addresses,
        sentinel_kwargs=timeouts,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_timeout_seconds,
    )
    redis = sentinel.master_for(settings.redis_master_name)
    cache = FlightCache(redis, settings.cache_flight_ttl_seconds, settings.cache_search_ttl_seconds)

    server = grpc.aio.server(interceptors=[ApiKeyAuthInterceptor(settings.flight_service_api_key)])
    servicer = FlightServicer(cache, drop_reserve_responses=settings.fault_drop_reserve_responses)
    pb_grpc.add_FlightServiceServicer_to_server(servicer, server)
    # Reflection — чтобы grpcurl работал без локальных .proto (тоже требует API key)
    reflection.enable_server_reflection(
        (pb.DESCRIPTOR.services_by_name["FlightService"].full_name, reflection.SERVICE_NAME),
        server,
    )
    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    await server.start()
    logger.info("flight-service started", extra={"fields": {"port": settings.grpc_port}})

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("flight-service stopping")
    await server.stop(grace=5)
    await redis.aclose()
    await engine.dispose()


def main() -> None:
    setup_logging(settings.log_level)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
