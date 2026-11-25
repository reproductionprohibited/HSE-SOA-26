-- migrate:up
GRANT SELECT ON analytics.agg_top_movies TO grafana;

-- migrate:down
REVOKE SELECT ON analytics.agg_top_movies FROM grafana;
