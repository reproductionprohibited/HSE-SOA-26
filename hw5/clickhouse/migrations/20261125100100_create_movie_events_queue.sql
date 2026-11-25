-- migrate:up
-- Консьюмер топика movie-events. Колонки совпадают с полями Avro-схемы schemas/movie_event.avsc
-- (имена и enum-значения один в один). Брокеры, топик и consumer group заданы named collection
-- movie_events_kafka (clickhouse/config.d/kafka.xml), список брокеров берётся из env KAFKA_BROKERS.
CREATE TABLE IF NOT EXISTS movie_events_queue
(
    event_id         UUID,
    user_id          String,
    movie_id         String,
    event_type       Enum8('VIEW_STARTED' = 1, 'VIEW_FINISHED' = 2, 'VIEW_PAUSED' = 3, 'VIEW_RESUMED' = 4, 'LIKED' = 5, 'SEARCHED' = 6),
    `timestamp`      DateTime64(3, 'UTC'),
    device_type      Enum8('MOBILE' = 1, 'DESKTOP' = 2, 'TV' = 3, 'TABLET' = 4),
    session_id       String,
    progress_seconds Nullable(Int32)
)
ENGINE = Kafka(movie_events_kafka);

-- migrate:down
DROP TABLE IF EXISTS movie_events_queue;
