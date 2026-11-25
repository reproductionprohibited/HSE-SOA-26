-- migrate:up
GRANT SELECT ON analytics.agg_device_daily TO grafana;

-- migrate:down
REVOKE SELECT ON analytics.agg_device_daily FROM grafana;
