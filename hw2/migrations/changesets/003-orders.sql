--liquibase formatted sql

--changeset marketplace:003-promo-codes
CREATE TYPE discount_type AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT');

CREATE TABLE promo_codes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             VARCHAR(20)    NOT NULL UNIQUE,
    discount_type    discount_type  NOT NULL,
    discount_value   NUMERIC(12, 2) NOT NULL CHECK (discount_value > 0),
    min_order_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (min_order_amount >= 0),
    max_uses         INTEGER        NOT NULL CHECK (max_uses > 0),
    current_uses     INTEGER        NOT NULL DEFAULT 0 CHECK (current_uses >= 0),
    valid_from       TIMESTAMPTZ    NOT NULL,
    valid_until      TIMESTAMPTZ    NOT NULL,
    active           BOOLEAN        NOT NULL DEFAULT TRUE,
    CHECK (current_uses <= max_uses),
    CHECK (valid_until > valid_from)
);
--rollback DROP TABLE promo_codes;
--rollback DROP TYPE discount_type;

--changeset marketplace:003-orders
CREATE TYPE order_status AS ENUM ('CREATED', 'PAYMENT_PENDING', 'PAID', 'SHIPPED', 'COMPLETED', 'CANCELED');

CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID           NOT NULL,
    status          order_status   NOT NULL DEFAULT 'CREATED',
    promo_code_id   UUID REFERENCES promo_codes (id),
    total_amount    NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_user_status ON orders (user_id, status);

-- Не больше одного активного заказа на пользователя — защита от гонки
-- двух параллельных POST /orders поверх проверки ORDER_HAS_ACTIVE в коде
CREATE UNIQUE INDEX uq_orders_one_active_per_user
    ON orders (user_id)
    WHERE status IN ('CREATED', 'PAYMENT_PENDING');

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
--rollback DROP TABLE orders;
--rollback DROP TYPE order_status;

--changeset marketplace:003-order-items
CREATE TABLE order_items (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id       UUID           NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id     UUID           NOT NULL REFERENCES products (id),
    quantity       INTEGER        NOT NULL CHECK (quantity BETWEEN 1 AND 999),
    price_at_order NUMERIC(12, 2) NOT NULL CHECK (price_at_order > 0),
    UNIQUE (order_id, product_id)
);
--rollback DROP TABLE order_items;

--changeset marketplace:003-user-operations
CREATE TYPE operation_type AS ENUM ('CREATE_ORDER', 'UPDATE_ORDER');

CREATE TABLE user_operations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID           NOT NULL,
    operation_type operation_type NOT NULL,
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Под запрос "последняя операция пользователя данного типа" (rate limit)
CREATE INDEX idx_user_operations_lookup
    ON user_operations (user_id, operation_type, created_at DESC);
--rollback DROP TABLE user_operations;
--rollback DROP TYPE operation_type;
