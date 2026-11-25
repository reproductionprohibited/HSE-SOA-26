-- migrate:up
-- Рейтинг фильмов за день по числу просмотров. Храним все фильмы дня с рангом, top-N отбирается при чтении:
-- события за день только добавляются, поэтому фильм не может «выпасть» и оставить устаревшую строку.
CREATE TABLE IF NOT EXISTS agg_top_movies
(
    metric_date  Date,
    movie_id     String,
    views        UInt64,
    uniq_viewers UInt64,
    rank         UInt32,
    computed_at  DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (metric_date, movie_id);

-- migrate:down
DROP TABLE IF EXISTS agg_top_movies;
