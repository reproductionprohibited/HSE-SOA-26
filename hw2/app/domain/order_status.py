"""Модель состояний заказа."""

from app.errors import ApiError
from marketplace_api.models import ErrorCode, OrderStatus

ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({OrderStatus.PAYMENT_PENDING, OrderStatus.CANCELED}),
    OrderStatus.PAYMENT_PENDING: frozenset({OrderStatus.PAID, OrderStatus.CANCELED}),
    OrderStatus.PAID: frozenset({OrderStatus.SHIPPED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELED: frozenset(),
}

# Статусы, в которых заказ считается активным
ACTIVE_STATUSES = (OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING)


def ensure_transition_allowed(current: OrderStatus, target: OrderStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ApiError(
            ErrorCode.INVALID_STATE_TRANSITION,
            f"Transition {current.value} -> {target.value} is not allowed",
            {"current_status": current.value, "target_status": target.value},
        )
