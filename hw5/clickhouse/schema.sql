
--
-- Database schema
--

CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE analytics.agg_daily_metrics
(
    `metric_date` Date,
    `metric_name` LowCardinality(String),
    `value` Float64,
    `computed_at` DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, metric_name)
SETTINGS index_granularity = 8192;

CREATE TABLE analytics.agg_device_daily
(
    `metric_date` Date,
    `device_type` Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    `users` UInt64,
    `events` UInt64,
    `computed_at` DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, device_type)
SETTINGS index_granularity = 8192;

CREATE TABLE analytics.agg_retention_cohort
(
    `cohort_date` Date,
    `day_n` UInt8,
    `cohort_size` UInt64,
    `retained` UInt64,
    `rate` Float64,
    `computed_at` DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (cohort_date, day_n)
SETTINGS index_granularity = 8192;

CREATE TABLE analytics.agg_top_movies
(
    `metric_date` Date,
    `movie_id` String,
    `views` UInt64,
    `uniq_viewers` UInt64,
    `rank` UInt32,
    `computed_at` DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, movie_id)
SETTINGS index_granularity = 8192;

CREATE TABLE analytics.movie_events
(
    `event_id` UUID,
    `user_id` String,
    `movie_id` String,
    `event_type` Enum8('VIEW_STARTED' = 1, 'VIEW_FINISHED' = 2, 'VIEW_PAUSED' = 3, 'VIEW_RESUMED' = 4, 'LIKED' = 5, 'SEARCHED' = 6),
    `event_time` DateTime64(3, 'UTC'),
    `event_date` Date MATERIALIZED toDate(event_time),
    `device_type` Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    `session_id` String,
    `progress_seconds` Nullable(UInt32),
    `ingested_at` DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, event_type, user_id, event_id)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW analytics.movie_events_mv TO analytics.movie_events
(
    `event_id` UUID,
    `user_id` String,
    `movie_id` String,
    `event_type` Enum8('VIEW_STARTED' = 1, 'VIEW_FINISHED' = 2, 'VIEW_PAUSED' = 3, 'VIEW_RESUMED' = 4, 'LIKED' = 5, 'SEARCHED' = 6),
    `event_time` DateTime64(3, 'UTC'),
    `device_type` Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    `session_id` String,
    `progress_seconds` Nullable(UInt32)
)
AS SELECT
    event_id,
    user_id,
    movie_id,
    event_type,
    timestamp AS event_time,
    device_type,
    session_id,
    CAST(progress_seconds, 'Nullable(UInt32)') AS progress_seconds
FROM analytics.movie_events_queue;

CREATE TABLE analytics.movie_events_queue
(
    `event_id` UUID,
    `user_id` String,
    `movie_id` String,
    `event_type` Enum8('VIEW_STARTED' = 1, 'VIEW_FINISHED' = 2, 'VIEW_PAUSED' = 3, 'VIEW_RESUMED' = 4, 'LIKED' = 5, 'SEARCHED' = 6),
    `timestamp` DateTime64(3, 'UTC'),
    `device_type` Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    `session_id` String,
    `progress_seconds` Nullable(Int32)
)
ENGINE = Kafka(movie_events_kafka);

CREATE TABLE analytics.schema_migrations
(
    `version` String,
    `ts` DateTime DEFAULT now(),
    `applied` UInt8 DEFAULT 1
)
ENGINE = ReplacingMergeTree(ts)
PRIMARY KEY version
ORDER BY version
SETTINGS index_granularity = 8192;


--
-- Dbmate schema migrations
--

INSERT INTO schema_migrations (version) VALUES
    ('20261125100000'),
    ('20261125100100'),
    ('20261125100200'),
    ('20261125200000'),
    ('20261125200100'),
    ('20261125200200'),
    ('20261125200300'),
    ('20261125300000'),
    ('20261125300001'),
    ('20261125300002'),
    ('20261125300003'),
    ('20261125300004');
