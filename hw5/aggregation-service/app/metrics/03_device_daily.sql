-- Активные пользователи и события по типам устройств за день {date}.
INSERT INTO agg_device_daily (metric_date, device_type, users, events, computed_at)
SELECT
    {date:Date} AS metric_date,
    device_type,
    uniqExact(user_id) AS users,
    count()            AS events,
    now64(3, 'UTC')    AS computed_at
FROM movie_events FINAL
WHERE event_date = {date:Date}
GROUP BY device_type
