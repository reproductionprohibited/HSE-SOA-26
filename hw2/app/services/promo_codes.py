from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromoCode
from app.db.session import SessionFactory
from app.errors import ApiError
from marketplace_api.models import DiscountType, ErrorCode, PromoCodeCreate

CENT = Decimal("0.01")

# PERCENTAGE: скидка не может превышать 70% суммы, иначе заказ оплачивается полностью
MAX_PERCENTAGE_DISCOUNT = Decimal("70")


async def lock_by_code(session: AsyncSession, code: str) -> PromoCode:
    promo = await session.scalar(
        select(PromoCode)
        .where(PromoCode.code == code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if promo is None:
        raise ApiError(ErrorCode.PROMO_CODE_INVALID, "Promo code not found", {"code": code, "reason": "NOT_FOUND"})
    return promo


async def lock_by_id(session: AsyncSession, promo_id: UUID) -> PromoCode:
    # populate_existing: объект мог быть загружен раньше без блокировки — перечитываем актуальные значения
    return await session.scalar(
        select(PromoCode)
        .where(PromoCode.id == promo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def validate(promo: PromoCode, now: datetime, order_amount: Decimal, *, already_applied: bool = False) -> None:
    """Проверки промокода из п.7 задания. already_applied — промокод уже учтён в current_uses этим заказом."""
    reason = None
    if not promo.active:
        reason = "INACTIVE"
    elif (promo.current_uses > promo.max_uses) if already_applied else (promo.current_uses >= promo.max_uses):
        reason = "EXHAUSTED"
    elif now < promo.valid_from:
        reason = "NOT_STARTED"
    elif now > promo.valid_until:
        reason = "EXPIRED"
    if reason is not None:
        raise ApiError(ErrorCode.PROMO_CODE_INVALID, "Promo code is not applicable", {"code": promo.code, "reason": reason})

    if order_amount < promo.min_order_amount:
        raise ApiError(
            ErrorCode.PROMO_CODE_MIN_AMOUNT,
            "Order amount is below promo code minimum",
            {"code": promo.code, "min_order_amount": promo.min_order_amount, "order_amount": order_amount},
        )


def calculate_discount(promo: PromoCode, amount: Decimal) -> Decimal:
    if promo.discount_type == DiscountType.PERCENTAGE:
        if promo.discount_value > MAX_PERCENTAGE_DISCOUNT:
            return Decimal("0")
        return (amount * promo.discount_value / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return min(promo.discount_value, amount)


class PromoCodeService:
    async def create(self, data: PromoCodeCreate) -> PromoCode:
        errors = []
        if data.valid_until <= data.valid_from:
            errors.append({"field": "body.valid_until", "message": "Must be after valid_from", "type": "invalid_range"})
        if data.discount_type == DiscountType.PERCENTAGE and data.discount_value > 100:
            errors.append({"field": "body.discount_value", "message": "Percentage must be <= 100", "type": "less_than_equal"})
        if errors:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "Request validation failed", {"fields": errors})

        async with SessionFactory() as session, session.begin():
            exists = await session.scalar(select(PromoCode.id).where(PromoCode.code == data.code))
            if exists is not None:
                raise ApiError(ErrorCode.PROMO_CODE_ALREADY_EXISTS, "Promo code already exists", {"code": data.code})
            fields = data.model_dump()
            # Необязательные поля с default в контракте: явный null трактуем как значение по умолчанию
            fields["min_order_amount"] = Decimal(fields["min_order_amount"] or 0)
            fields["active"] = True if fields["active"] is None else fields["active"]
            promo = PromoCode(**fields)
            session.add(promo)
        return promo
