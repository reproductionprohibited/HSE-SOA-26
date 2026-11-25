-- migrate:up
GRANT SELECT ON analytics.agg_daily_metrics TO grafana;

-- migrate:down
REVOKE SELECT ON analytics.agg_daily_metrics FROM grafana;
