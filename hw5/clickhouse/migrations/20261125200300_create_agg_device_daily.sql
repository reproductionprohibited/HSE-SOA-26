-- migrate:up
-- Активность по типам устройств за день (для дашборда).
CREATE TABLE IF NOT EXISTS agg_device_daily
(
    metric_date Date,
    device_type Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    users       UInt64,
    events      UInt64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, device_type);

-- migrate:down
DROP TABLE IF EXISTS agg_device_daily;
