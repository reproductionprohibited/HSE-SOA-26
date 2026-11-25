-- Рейтинг фильмов за день {date} по числу просмотров (VIEW_STARTED); rank — оконная row_number().
INSERT INTO agg_top_movies (metric_date, movie_id, views, uniq_viewers, rank, computed_at)
SELECT
    {date:Date} AS metric_date,
    movie_id,
    views,
    uniq_viewers,
    row_number() OVER (ORDER BY views DESC, uniq_viewers DESC, movie_id) AS rank,
    now64(3, 'UTC') AS computed_at
FROM
(
    SELECT
        movie_id,
        countIf(event_type = 'VIEW_STARTED')              AS views,
        uniqExactIf(user_id, event_type = 'VIEW_STARTED') AS uniq_viewers
    FROM movie_events FINAL
    WHERE event_date = {date:Date}
    GROUP BY movie_id
    HAVING views > 0
)
