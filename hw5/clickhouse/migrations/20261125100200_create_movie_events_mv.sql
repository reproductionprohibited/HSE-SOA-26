-- migrate:up
-- Перекладка из Kafka-очереди в MergeTree.
CREATE MATERIALIZED VIEW IF NOT EXISTS movie_events_mv TO movie_events AS
SELECT
    event_id,
    user_id,
    movie_id,
    event_type,
    `timestamp` AS event_time,
    device_type,
    session_id,
    CAST(progress_seconds AS Nullable(UInt32)) AS progress_seconds
FROM movie_events_queue;

-- migrate:down
DROP VIEW IF EXISTS movie_events_mv;
