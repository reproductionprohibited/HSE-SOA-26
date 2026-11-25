-- DAU, среднее время просмотра и конверсия за день {date}.
-- Конверсия — по сессиям: доля сессий с VIEW_STARTED, дошедших до VIEW_FINISHED.
-- Метрики без данных (NaN/inf при пустом дне) не пишем.
INSERT INTO agg_daily_metrics (metric_date, metric_name, value, computed_at)
SELECT
    {date:Date} AS metric_date,
    m.1 AS metric_name,
    m.2 AS value,
    now64(3, 'UTC') AS computed_at
FROM
(
    SELECT
        uniqExact(user_id)                                        AS dau,
        avgIf(progress_seconds, event_type = 'VIEW_FINISHED')     AS avg_watch_seconds,
        uniqExactIf(session_id, event_type = 'VIEW_FINISHED')
            / uniqExactIf(session_id, event_type = 'VIEW_STARTED') AS view_conversion
    FROM movie_events FINAL
    WHERE event_date = {date:Date}
)
ARRAY JOIN [
    ('dau', toFloat64(dau)),
    ('avg_watch_seconds', toFloat64(avg_watch_seconds)),
    ('view_conversion', toFloat64(view_conversion))
] AS m
WHERE isFinite(m.2)
