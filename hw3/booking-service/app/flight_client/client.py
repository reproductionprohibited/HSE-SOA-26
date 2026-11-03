"""gRPC-клиент Flight Service.

Ошибки вызовов пробрасываются как grpc.aio.AioRpcError, отказ circuit breaker — как CircuitOpenError.
"""

import uuid
from datetime import date

import grpc
from flight.v1 import flight_service_pb2 as pb
from flight.v1 import flight_service_pb2_grpc as pb_grpc

from app.flight_client.circuit_breaker import CircuitBreaker
from app.flight_client.interceptors import ApiKeyInterceptor, CircuitBreakerInterceptor, RetryInterceptor

# После падения сервера канал по умолчанию ждёт до 1 с перед переподключением и до 30 с
# перед повторным DNS-резолвом — после рестарта Flight Service запросы «оживали» бы с задержкой
_CHANNEL_OPTIONS = [
    ("grpc.initial_reconnect_backoff_ms", 100),
    ("grpc.min_reconnect_backoff_ms", 100),
    ("grpc.max_reconnect_backoff_ms", 1000),
    ("grpc.dns_min_time_between_resolutions_ms", 500),
]


class FlightClient:
    def __init__(
        self,
        address: str,
        timeout_seconds: float,
        api_key: str,
        breaker: CircuitBreaker,
        retry_max_attempts: int,
        retry_initial_backoff_ms: int,
    ) -> None:
        # Один долгоживущий канал на процесс: HTTP/2-соединение переиспользуется всеми запросами
        self._channel = grpc.aio.insecure_channel(
            address,
            options=_CHANNEL_OPTIONS,
            interceptors=[
                CircuitBreakerInterceptor(breaker),
                RetryInterceptor(retry_max_attempts, retry_initial_backoff_ms),
                ApiKeyInterceptor(api_key),
            ],
        )
        self._stub = pb_grpc.FlightServiceStub(self._channel)
        self._timeout = timeout_seconds

    async def close(self) -> None:
        await self._channel.close()

    async def search_flights(self, origin: str, destination: str, departure_date: date | None) -> list[pb.Flight]:
        request = pb.SearchFlightsRequest(origin=origin, destination=destination)
        if departure_date is not None:
            request.date.CopyFrom(pb.Date(year=departure_date.year, month=departure_date.month, day=departure_date.day))
        response = await self._stub.SearchFlights(request, timeout=self._timeout)
        return list(response.flights)

    async def get_flight(self, flight_id: uuid.UUID) -> pb.Flight:
        return await self._stub.GetFlight(pb.GetFlightRequest(flight_id=str(flight_id)), timeout=self._timeout)

    async def reserve_seats(self, flight_id: uuid.UUID, seat_count: int, booking_id: uuid.UUID) -> pb.SeatReservation:
        request = pb.ReserveSeatsRequest(flight_id=str(flight_id), seat_count=seat_count, booking_id=str(booking_id))
        return await self._stub.ReserveSeats(request, timeout=self._timeout)

    async def release_reservation(self, booking_id: uuid.UUID) -> pb.SeatReservation:
        request = pb.ReleaseReservationRequest(booking_id=str(booking_id))
        return await self._stub.ReleaseReservation(request, timeout=self._timeout)
