--liquibase formatted sql

--changeset marketplace:004-seed-promo-codes
-- Набор промокодов под все ветки проверок при создании заказа
INSERT INTO promo_codes (code, discount_type, discount_value, min_order_amount, max_uses, current_uses, valid_from, valid_until, active)
VALUES
    ('SALE10',     'PERCENTAGE',   10,   0,      1000, 0, now() - interval '1 day',  now() + interval '1 year', TRUE),  -- валидный, 10%
    ('MINUS500',   'FIXED_AMOUNT', 500,  1000,   1000, 0, now() - interval '1 day',  now() + interval '1 year', TRUE),  -- валидный, -500 от суммы >= 1000
    ('BIGORDER',   'PERCENTAGE',   15,   100000, 1000, 0, now() - interval '1 day',  now() + interval '1 year', TRUE),  -- PROMO_CODE_MIN_AMOUNT
    ('MEGA80',     'PERCENTAGE',   80,   0,      1000, 0, now() - interval '1 day',  now() + interval '1 year', TRUE),  -- скидка > 70%
    ('EXPIRED',    'PERCENTAGE',   20,   0,      1000, 0, now() - interval '1 year', now() - interval '1 day',  TRUE),  -- истёк
    ('NOTYET',     'PERCENTAGE',   20,   0,      1000, 0, now() + interval '1 year', now() + interval '2 years', TRUE), -- ещё не начался
    ('USEDUP',     'PERCENTAGE',   20,   0,      1,    1, now() - interval '1 day',  now() + interval '1 year', TRUE),  -- исчерпан
    ('DISABLED',   'PERCENTAGE',   20,   0,      1000, 0, now() - interval '1 day',  now() + interval '1 year', FALSE); -- неактивен
--rollback DELETE FROM promo_codes WHERE code IN ('SALE10', 'MINUS500', 'BIGORDER', 'MEGA80', 'EXPIRED', 'NOTYET', 'USEDUP', 'DISABLED');
