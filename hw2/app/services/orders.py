"""Бизнес-логика заказов

Каждая операция — одна транзакция: при любой ошибке откатываются и резервы
остатков, и изменения промокода. Порядок захвата блокировок везде одинаковый
(пользователь → заказ → товары по id → промокод), чтобы не ловить дедлоки.
"""

import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import Principal
from app.config import settings
from app.db.models import OperationType, Order, OrderItem, Product, UserOperation
from app.db.session import SessionFactory
from app.domain.order_status import ACTIVE_STATUSES, ensure_transition_allowed
from app.errors import ApiError
from app.services import promo_codes
from marketplace_api.models import (
    ErrorCode,
    OrderCreate,
    OrderItemRequest,
    OrderStatus,
    OrderUpdate,
    ProductStatus,
    UserRole,
)

MAX_ITEM_QUANTITY = 999


# ---------- общие шаги ----------


def _merge_items(items: list[OrderItemRequest]) -> dict[UUID, int]:
    """Позиции с одинаковым product_id сводятся в одну (в order_items пара order+product уникальна)."""
    merged: dict[UUID, int] = {}
    for item in items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.quantity
    too_big = [pid for pid, qty in merged.items() if qty > MAX_ITEM_QUANTITY]
    if too_big:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed",
            {"fields": [
                {"field": "body.items", "message": f"Total quantity of product {pid} exceeds {MAX_ITEM_QUANTITY}", "type": "less_than_equal"}
                for pid in too_big
            ]},
        )
    return merged


async def _db_now(session: AsyncSession) -> datetime:
    return await session.scalar(select(func.now()))


async def _lock_user(session: AsyncSession, user_id: UUID) -> None:
    # блокировка на пользователя до конца транзакции: параллельные запросы одного
    # пользователя выполняются по очереди, и проверки лимита/активного заказа не обходятся гонкой
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(user_id), 0))))


async def _check_rate_limit(session: AsyncSession, user_id: UUID, operation: OperationType) -> None:
    last = await session.scalar(
        select(func.max(UserOperation.created_at)).where(
            UserOperation.user_id == user_id, UserOperation.operation_type == operation
        )
    )
    if last is None:
        return
    wait = last + timedelta(minutes=settings.order_rate_limit_minutes) - await _db_now(session)
    if wait > timedelta(0):
        raise ApiError(
            ErrorCode.ORDER_LIMIT_EXCEEDED,
            f"Too many {operation.value} operations, try again later",
            {"operation_type": operation.value, "retry_after_seconds": math.ceil(wait.total_seconds())},
        )


async def _check_no_active_order(session: AsyncSession, user_id: UUID) -> None:
    active_id = await session.scalar(
        select(Order.id).where(Order.user_id == user_id, Order.status.in_(ACTIVE_STATUSES)).limit(1)
    )
    if active_id is not None:
        raise ApiError(ErrorCode.ORDER_HAS_ACTIVE, "User already has an active order", {"order_id": active_id})


async def _lock_products(session: AsyncSession, product_ids: Iterable[UUID]) -> dict[UUID, Product]:
    # SELECT ... FOR UPDATE в порядке id: остатки не изменит параллельный заказ
    products = await session.scalars(
        select(Product)
        .where(Product.id.in_(list(product_ids)))
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {p.id: p for p in products}


def _check_catalog(products: dict[UUID, Product], wanted: dict[UUID, int]) -> None:
    missing = [pid for pid in wanted if pid not in products]
    if missing:
        raise ApiError(ErrorCode.PRODUCT_NOT_FOUND, "Product not found", {"product_ids": missing})
    inactive = [pid for pid in wanted if products[pid].status != ProductStatus.ACTIVE]
    if inactive:
        raise ApiError(ErrorCode.PRODUCT_INACTIVE, "Product is not active", {"product_ids": inactive})


def _check_stock(products: dict[UUID, Product], wanted: dict[UUID, int]) -> None:
    shortages = [
        {"product_id": pid, "requested": qty, "available": products[pid].stock}
        for pid, qty in wanted.items()
        if products[pid].stock < qty
    ]
    if shortages:
        raise ApiError(ErrorCode.INSUFFICIENT_STOCK, "Insufficient stock", {"items": shortages})


def _reserve(products: dict[UUID, Product], wanted: dict[UUID, int]) -> list[OrderItem]:
    """Списывает остатки и фиксирует снапшот цены в позиции заказа."""
    items = []
    for pid, qty in wanted.items():
        product = products[pid]
        product.stock -= qty
        items.append(OrderItem(product_id=pid, quantity=qty, price_at_order=product.price))
    return items


def _release(products: dict[UUID, Product], items: Iterable[OrderItem]) -> None:
    for item in items:
        products[item.product_id].stock += item.quantity


def _subtotal(items: list[OrderItem]) -> Decimal:
    return sum((item.price_at_order * item.quantity for item in items), Decimal("0"))


async def _get_owned_order(session: AsyncSession, order_id: UUID, actor: Principal, *, for_update: bool) -> Order:
    query = select(Order).where(Order.id == order_id)
    if for_update:
        query = query.with_for_update(of=Order)
    order = await session.scalar(query)
    if order is None:
        raise ApiError(ErrorCode.ORDER_NOT_FOUND, "Order not found", {"order_id": order_id})
    # USER — только свои заказы, ADMIN — любые (роль проверена в handlers)
    if actor.role != UserRole.ADMIN and order.user_id != actor.user_id:
        raise ApiError(ErrorCode.ORDER_OWNERSHIP_VIOLATION, "Order belongs to another user", {"order_id": order_id})
    return order


# ---------- сценарии ----------


class OrderService:
    async def get(self, actor: Principal, order_id: UUID) -> Order:
        async with SessionFactory() as session:
            return await _get_owned_order(session, order_id, actor, for_update=False)

    async def create(self, actor: Principal, data: OrderCreate) -> Order:
        user_id = actor.user_id
        wanted = _merge_items(data.items)

        async with SessionFactory() as session, session.begin():
            await _lock_user(session, user_id)

            # 1. Ограничение частоты создания
            await _check_rate_limit(session, user_id, OperationType.CREATE_ORDER)
            # 2. Нет активных заказов
            await _check_no_active_order(session, user_id)
            # 3. Товары существуют и ACTIVE
            products = await _lock_products(session, wanted)
            _check_catalog(products, wanted)
            # 4. Хватает остатков
            _check_stock(products, wanted)
            # 5–6. Резерв остатков + снапшот цен
            items = _reserve(products, wanted)

            # 7. Расчёт стоимости и промокод
            subtotal = _subtotal(items)
            promo, discount = None, Decimal("0")
            if data.promo_code is not None:
                promo = await promo_codes.lock_by_code(session, data.promo_code)
                promo_codes.validate(promo, await _db_now(session), subtotal)
                discount = promo_codes.calculate_discount(promo, subtotal)
                promo.current_uses += 1

            # 8. Сохранение заказа и фиксация операции
            order = Order(
                user_id=user_id,
                status=OrderStatus.CREATED,
                promo_code=promo,
                total_amount=subtotal - discount,
                discount_amount=discount,
                items=items,
            )
            session.add(order)
            session.add(UserOperation(user_id=user_id, operation_type=OperationType.CREATE_ORDER))
        return order

    async def update(self, actor: Principal, order_id: UUID, data: OrderUpdate) -> Order:
        # Лимит частоты и запись в user_operations — по тому, кто выполняет операцию
        user_id = actor.user_id
        wanted = _merge_items(data.items)

        async with SessionFactory() as session, session.begin():
            await _lock_user(session, user_id)

            # 1. Владелец
            order = await _get_owned_order(session, order_id, actor, for_update=True)
            # 2. Обновление только в CREATED
            if order.status != OrderStatus.CREATED:
                raise ApiError(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    f"Order can be updated only in status CREATED, current status is {order.status.value}",
                    {"current_status": order.status.value},
                )
            # 3. Ограничение частоты обновления
            await _check_rate_limit(session, user_id, OperationType.UPDATE_ORDER)

            products = await _lock_products(session, {i.product_id for i in order.items} | wanted.keys())
            # 4. Возврат остатков по текущим позициям
            _release(products, order.items)
            # 5. Проверка и резервирование новых позиций
            _check_catalog(products, wanted)
            _check_stock(products, wanted)
            new_items = _reserve(products, wanted)

            order.items.clear()
            await session.flush()  # сначала удалить старые позиции: (order_id, product_id) уникальна
            order.items.extend(new_items)

            # 6. Пересчёт стоимости; промокод проверяется заново
            subtotal = _subtotal(new_items)
            discount = Decimal("0")
            if order.promo_code_id is not None:
                promo = await promo_codes.lock_by_id(session, order.promo_code_id)
                try:
                    promo_codes.validate(promo, await _db_now(session), subtotal, already_applied=True)
                    discount = promo_codes.calculate_discount(promo, subtotal)
                except ApiError:
                    # Промокод больше не применим — снимаем скидку и возвращаем использование
                    promo.current_uses -= 1
                    order.promo_code = None
            order.total_amount = subtotal - discount
            order.discount_amount = discount
            order.updated_at = func.now()  # даже если сумма не поменялась

            # 7. Фиксация операции
            session.add(UserOperation(user_id=user_id, operation_type=OperationType.UPDATE_ORDER))
            await session.flush()
            await session.refresh(order, ["updated_at"])
        return order

    async def cancel(self, actor: Principal, order_id: UUID) -> Order:
        async with SessionFactory() as session, session.begin():
            # 1. Владелец
            order = await _get_owned_order(session, order_id, actor, for_update=True)
            # 2. Отмена только из CREATED / PAYMENT_PENDING
            ensure_transition_allowed(order.status, OrderStatus.CANCELED)
            # 3. Возврат остатков
            products = await _lock_products(session, {i.product_id for i in order.items})
            _release(products, order.items)
            # 4. Возврат использования промокода
            if order.promo_code_id is not None:
                promo = await promo_codes.lock_by_id(session, order.promo_code_id)
                promo.current_uses -= 1
            # 5. Статус
            order.status = OrderStatus.CANCELED
        return order
