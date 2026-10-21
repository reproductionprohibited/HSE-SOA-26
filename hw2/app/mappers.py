"""ORM-сущности -> сгенерированные DTO ответов."""

from app.db.models import Order, Product, PromoCode, User
from marketplace_api.models import (
    OrderItemResponse,
    OrderResponse,
    ProductPage,
    ProductResponse,
    PromoCodeResponse,
    UserResponse,
)


def product_to_response(product: Product) -> ProductResponse:
    return ProductResponse.model_validate(product, from_attributes=True)


def products_to_page(products: list[Product], total: int, page: int, size: int) -> ProductPage:
    return ProductPage(
        content=[product_to_response(p) for p in products],
        totalElements=total,
        page=page,
        size=size,
    )


def order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        status=order.status,
        items=[OrderItemResponse.model_validate(item, from_attributes=True) for item in order.items],
        promo_code=order.promo_code.code if order.promo_code is not None else None,
        total_amount=order.total_amount,
        discount_amount=order.discount_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def promo_code_to_response(promo: PromoCode) -> PromoCodeResponse:
    return PromoCodeResponse.model_validate(promo, from_attributes=True)


def user_to_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)
