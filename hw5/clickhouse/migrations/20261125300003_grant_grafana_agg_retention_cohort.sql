-- migrate:up
GRANT SELECT ON analytics.agg_retention_cohort TO grafana;

-- migrate:down
REVOKE SELECT ON analytics.agg_retention_cohort FROM grafana;
