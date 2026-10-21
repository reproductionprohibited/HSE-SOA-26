"""Реализация сгенерированного интерфейса MarketplaceApi.

Тонкий слой: проверяет роль по матрице доступа, принимает сгенерированные DTO
и делегирует в сервисы. Проверки «только свои» требуют данных из БД и выполняются в сервисах.
"""

from uuid import UUID

from app.auth.dependencies import require_roles
from app.auth.tokens import Principal
from app.mappers import (
    order_to_response,
    product_to_response,
    products_to_page,
    promo_code_to_response,
    user_to_response,
)
from app.services.auth import AuthService
from app.services.orders import OrderService
from app.services.products import ProductService
from app.services.promo_codes import PromoCodeService
from marketplace_api.api import MarketplaceApi
from marketplace_api.models import (
    LoginRequest,
    OrderCreate,
    OrderResponse,
    OrderUpdate,
    ProductCreate,
    ProductPage,
    ProductResponse,
    ProductStatus,
    ProductUpdate,
    PromoCodeCreate,
    PromoCodeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserRole,
)

USER, SELLER, ADMIN = UserRole.USER, UserRole.SELLER, UserRole.ADMIN


class MarketplaceApiImpl(MarketplaceApi):
    def __init__(self) -> None:
        self.auth = AuthService()
        self.products = ProductService()
        self.orders = OrderService()
        self.promo_codes = PromoCodeService()

    # ---------- auth ----------

    async def register(self, body: RegisterRequest) -> UserResponse:
        return user_to_response(await self.auth.register(body))

    async def login(self, body: LoginRequest) -> TokenResponse:
        return await self.auth.login(body)

    async def refresh(self, body: RefreshRequest) -> TokenResponse:
        return await self.auth.refresh(body)

    # ---------- products ----------

    async def create_product(self, principal: Principal, body: ProductCreate) -> ProductResponse:
        require_roles(principal, SELLER, ADMIN)
        return product_to_response(await self.products.create(body, principal))

    async def list_products(
        self, principal: Principal, page: int, size: int, status: ProductStatus | None, category: str | None
    ) -> ProductPage:
        products, total = await self.products.list(page, size, status, category)
        return products_to_page(products, total, page, size)

    async def get_product(self, principal: Principal, id: UUID) -> ProductResponse:
        return product_to_response(await self.products.get(id))

    async def update_product(self, principal: Principal, id: UUID, body: ProductUpdate) -> ProductResponse:
        require_roles(principal, SELLER, ADMIN)
        return product_to_response(await self.products.update(id, body, principal))

    async def delete_product(self, principal: Principal, id: UUID) -> ProductResponse:
        require_roles(principal, SELLER, ADMIN)
        return product_to_response(await self.products.archive(id, principal))

    # ---------- orders ----------

    async def create_order(self, principal: Principal, body: OrderCreate) -> OrderResponse:
        require_roles(principal, USER, ADMIN)
        return order_to_response(await self.orders.create(principal, body))

    async def get_order(self, principal: Principal, id: UUID) -> OrderResponse:
        require_roles(principal, USER, ADMIN)
        return order_to_response(await self.orders.get(principal, id))

    async def update_order(self, principal: Principal, id: UUID, body: OrderUpdate) -> OrderResponse:
        require_roles(principal, USER, ADMIN)
        return order_to_response(await self.orders.update(principal, id, body))

    async def cancel_order(self, principal: Principal, id: UUID) -> OrderResponse:
        require_roles(principal, USER, ADMIN)
        return order_to_response(await self.orders.cancel(principal, id))

    # ---------- promo codes ----------

    async def create_promo_code(self, principal: Principal, body: PromoCodeCreate) -> PromoCodeResponse:
        require_roles(principal, SELLER, ADMIN)
        return promo_code_to_response(await self.promo_codes.create(body))
