-- migrate:up
-- Постоянное хранилище raw-событий.
-- ReplacingMergeTree: доставка из Kafka at-least-once, дубли с одним event_id схлопываются при merge.
-- ORDER BY: все метрики фильтруют по дате и типу события; uniq(user_id) и retention выигрывают от
-- сортировки по пользователю; event_id в конце делает ключ уникальным.
CREATE TABLE IF NOT EXISTS movie_events
(
    event_id         UUID,
    user_id          String,
    movie_id         String,
    event_type       Enum8('VIEW_STARTED' = 1, 'VIEW_FINISHED' = 2, 'VIEW_PAUSED' = 3, 'VIEW_RESUMED' = 4, 'LIKED' = 5, 'SEARCHED' = 6),
    event_time       DateTime64(3, 'UTC'),
    event_date       Date MATERIALIZED toDate(event_time),
    device_type      Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    session_id       String,
    progress_seconds Nullable(UInt32),
    ingested_at      DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, event_type, user_id, event_id);

-- migrate:down
DROP TABLE IF EXISTS movie_events;
