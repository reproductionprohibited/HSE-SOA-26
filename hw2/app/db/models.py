"""ORM-модели таблиц. Схемой владеет Liquibase (migrations/), здесь только маппинг."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, FetchedValue, ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from marketplace_api.models import DiscountType, OrderStatus, ProductStatus, UserRole


class OperationType(enum.Enum):
    CREATE_ORDER = "CREATE_ORDER"
    UPDATE_ORDER = "UPDATE_ORDER"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    # Типы создаются миграциями, SQLAlchemy их только использует
    return Enum(enum_cls, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])


Money = Numeric(12, 2)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}

    # Подтягивать серверные значения (created_at, updated_at из триггера) сразу после INSERT/UPDATE
    __mapper_args__ = {"eager_defaults": True}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(4000))
    price: Mapped[Decimal] = mapped_column(Money)
    stock: Mapped[int]
    category: Mapped[str] = mapped_column(String(100))
    status: Mapped[ProductStatus] = mapped_column(pg_enum(ProductStatus, "product_status"))
    seller_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), server_onupdate=FetchedValue())  # триггер set_updated_at


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    discount_type: Mapped[DiscountType] = mapped_column(pg_enum(DiscountType, "discount_type"))
    discount_value: Mapped[Decimal] = mapped_column(Money)
    min_order_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    max_uses: Mapped[int]
    current_uses: Mapped[int] = mapped_column(default=0)
    valid_from: Mapped[datetime]
    valid_until: Mapped[datetime]
    active: Mapped[bool] = mapped_column(default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]
    status: Mapped[OrderStatus] = mapped_column(pg_enum(OrderStatus, "order_status"))
    promo_code_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("promo_codes.id"))
    total_amount: Mapped[Decimal] = mapped_column(Money)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), server_onupdate=FetchedValue())  # триггер set_updated_at

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    promo_code: Mapped[PromoCode | None] = relationship(lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    price_at_order: Mapped[Decimal] = mapped_column(Money)

    order: Mapped[Order] = relationship(back_populates="items")


class UserOperation(Base):
    __tablename__ = "user_operations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]
    operation_type: Mapped[OperationType] = mapped_column(pg_enum(OperationType, "operation_type"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
