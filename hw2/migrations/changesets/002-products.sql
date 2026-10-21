--liquibase formatted sql

--changeset marketplace:002-products
CREATE TYPE product_status AS ENUM ('ACTIVE', 'INACTIVE', 'ARCHIVED');

CREATE TABLE products (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255)   NOT NULL,
    description VARCHAR(4000),
    price       NUMERIC(12, 2) NOT NULL CHECK (price > 0),
    stock       INTEGER        NOT NULL CHECK (stock >= 0),
    category    VARCHAR(100)   NOT NULL,
    status      product_status NOT NULL DEFAULT 'ACTIVE',
    seller_id   UUID,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_status ON products (status);
CREATE INDEX idx_products_category ON products (category);

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
--rollback DROP TABLE products;
--rollback DROP TYPE product_status;
