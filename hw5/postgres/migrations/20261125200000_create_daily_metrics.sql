-- migrate:up
-- Готовые метрики для других сервисов, дашбордов и экспорта в S3.
-- PK (metric_date, metric_name, dimension) делает запись идемпотентной: пересчёт обновляет строку через
-- INSERT ... ON CONFLICT DO UPDATE.
CREATE TABLE daily_metrics (
    metric_date date             NOT NULL,
    metric_name text             NOT NULL,             -- dau, avg_watch_seconds, view_conversion, retention_d1, retention_d7, top_movie_views
    dimension   text             NOT NULL DEFAULT '',  -- movie_id для top_movie_views, '' для скалярных метрик
    value       double precision NOT NULL,
    computed_at timestamptz      NOT NULL,
    PRIMARY KEY (metric_date, metric_name, dimension)
);

-- migrate:down
DROP TABLE daily_metrics;
