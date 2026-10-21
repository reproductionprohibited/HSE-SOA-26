from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import Principal
from app.db.models import Product
from app.db.session import SessionFactory
from app.errors import ApiError
from marketplace_api.models import ErrorCode, ProductCreate, ProductStatus, ProductUpdate, UserRole


async def _get_or_404(session: AsyncSession, product_id: UUID) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise ApiError(ErrorCode.PRODUCT_NOT_FOUND, "Product not found", {"product_id": product_id})
    return product


def _ensure_can_manage(product: Product, actor: Principal) -> None:
    # SELLER управляет только своими товарами, ADMIN — любыми (роль проверена в handlers)
    if actor.role == UserRole.SELLER and product.seller_id != actor.user_id:
        raise ApiError(ErrorCode.ACCESS_DENIED, "Seller can manage only own products", {"product_id": product.id})


class ProductService:
    async def create(self, data: ProductCreate, actor: Principal) -> Product:
        async with SessionFactory() as session, session.begin():
            product = Product(**data.model_dump(), seller_id=actor.user_id)
            session.add(product)
        return product

    async def get(self, product_id: UUID) -> Product:
        async with SessionFactory() as session:
            return await _get_or_404(session, product_id)

    async def list(
        self, page: int, size: int, status: ProductStatus | None, category: str | None
    ) -> tuple[list[Product], int]:
        filters = []
        if status is not None:
            filters.append(Product.status == status)
        if category is not None:
            filters.append(Product.category == category)

        async with SessionFactory() as session:
            total = await session.scalar(select(func.count()).select_from(Product).where(*filters))
            products = await session.scalars(
                select(Product)
                .where(*filters)
                .order_by(Product.created_at.desc(), Product.id)
                .offset(page * size)
                .limit(size)
            )
            return list(products), total or 0

    async def update(self, product_id: UUID, data: ProductUpdate, actor: Principal) -> Product:
        async with SessionFactory() as session, session.begin():
            product = await _get_or_404(session, product_id)
            _ensure_can_manage(product, actor)
            for field, value in data.model_dump().items():
                setattr(product, field, value)
        return product

    async def archive(self, product_id: UUID, actor: Principal) -> Product:
        """Мягкое удаление: запись остаётся, статус меняется на ARCHIVED."""
        async with SessionFactory() as session, session.begin():
            product = await _get_or_404(session, product_id)
            _ensure_can_manage(product, actor)
            product.status = ProductStatus.ARCHIVED
        return product
