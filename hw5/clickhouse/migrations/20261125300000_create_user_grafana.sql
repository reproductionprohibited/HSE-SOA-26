-- migrate:up
-- Read-only пользователь для Grafana: видит только витрины agg_* (гранты в следующих миграциях),
-- raw-события movie_events ему недоступны. readonly=2 — только чтение, но клиент может менять настройки
-- запроса (нужно плагину Grafana).
CREATE USER IF NOT EXISTS grafana IDENTIFIED WITH sha256_password BY 'grafana' SETTINGS readonly = 2;

-- migrate:down
DROP USER IF EXISTS grafana;
