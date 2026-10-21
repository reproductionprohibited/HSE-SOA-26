--liquibase formatted sql

--changeset marketplace:005-users
CREATE TYPE user_role AS ENUM ('USER', 'SELLER', 'ADMIN');

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          user_role    NOT NULL DEFAULT 'USER',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- email уникален без учёта регистра
CREATE UNIQUE INDEX uq_users_email ON users (lower(email));
--rollback DROP TABLE users;
--rollback DROP TYPE user_role;

--changeset marketplace:005-users-foreign-keys
ALTER TABLE products ADD CONSTRAINT fk_products_seller FOREIGN KEY (seller_id) REFERENCES users (id);
ALTER TABLE orders ADD CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id);
ALTER TABLE user_operations ADD CONSTRAINT fk_user_operations_user FOREIGN KEY (user_id) REFERENCES users (id);
CREATE INDEX idx_products_seller ON products (seller_id);
--rollback DROP INDEX idx_products_seller;
--rollback ALTER TABLE user_operations DROP CONSTRAINT fk_user_operations_user;
--rollback ALTER TABLE orders DROP CONSTRAINT fk_orders_user;
--rollback ALTER TABLE products DROP CONSTRAINT fk_products_seller;

--changeset marketplace:005-seed-admin
-- ADMIN не регистрируется через API. Учётная запись для проверки: admin@marketplace.com / admin12345
INSERT INTO users (email, password_hash, role)
VALUES ('admin@marketplace.com', '$argon2id$v=19$m=65536,t=3,p=4$1L5yi1uBllL3+3xlSWYmQA$AZ0yqgbM+etKu1Kf0uP+xDDR592AV5UqdFZ0/wMo6Ns', 'ADMIN');
--rollback DELETE FROM users WHERE email = 'admin@marketplace.com';
