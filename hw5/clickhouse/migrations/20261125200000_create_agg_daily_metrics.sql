-- migrate:up
-- Скалярные метрики за день: dau, avg_watch_seconds, view_conversion, retention_d1, retention_d7.
-- ReplacingMergeTree(computed_at): пересчёт за дату заменяет строку, а не дублирует (читаем через FINAL).
CREATE TABLE IF NOT EXISTS agg_daily_metrics
(
    metric_date Date,
    metric_name LowCardinality(String),
    value       Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, metric_name);

-- migrate:down
DROP TABLE IF EXISTS agg_daily_metrics;
