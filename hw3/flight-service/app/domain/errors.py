"""Бизнес-ошибки Flight Service. О gRPC не знают — маппинг в status codes в grpc_handlers."""


class DomainError(Exception):
    pass


class InvalidArgument(DomainError):
    pass


class FlightNotFound(DomainError):
    def __init__(self, flight_id: object) -> None:
        super().__init__(f"flight {flight_id} not found")


class FlightAlreadyExists(DomainError):
    def __init__(self, flight_number: str) -> None:
        super().__init__(f"flight {flight_number} already exists on this departure date")


class FlightNotAvailable(DomainError):
    def __init__(self, flight_id: object, status: str) -> None:
        super().__init__(f"flight {flight_id} is {status}, only SCHEDULED flights can be booked")


class NotEnoughSeats(DomainError):
    def __init__(self, flight_id: object, requested: int, available: int) -> None:
        super().__init__(f"flight {flight_id}: requested {requested} seats, only {available} available")


class ReservationNotFound(DomainError):
    def __init__(self, booking_id: object) -> None:
        super().__init__(f"reservation for booking {booking_id} not found")


class ReservationAlreadyExists(DomainError):
    def __init__(self, booking_id: object) -> None:
        super().__init__(f"reservation for booking {booking_id} already exists with different flight or seat_count")


class InjectedResponseLoss(DomainError):
    """Fault injection для демо: операция выполнена, но клиент получает UNAVAILABLE."""

    def __init__(self) -> None:
        super().__init__("fault injection: response dropped")
