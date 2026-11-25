-- Когортный retention для когорт [{date} - 7, {date}].
-- Когорта пользователя — дата его первого VIEW_STARTED за всю историю. Для каждой когорты считаем
-- день жизни day_n = 0..min(7, {date} - cohort_date) и долю пользователей когорты, активных в этот день
-- (любое событие). День {date} даёт каждой из этих когорт новую точку, поэтому пересчитываем именно их.
-- Дни без вернувшихся пользователей тоже пишем (retained = 0), чтобы в когортной таблице не было дыр.
INSERT INTO agg_retention_cohort (cohort_date, day_n, cohort_size, retained, rate, computed_at)
WITH
    cohorts AS
    (
        SELECT user_id, min(event_date) AS cohort_date
        FROM movie_events
        WHERE event_type = 'VIEW_STARTED' AND event_date <= {date:Date}
        GROUP BY user_id
        HAVING cohort_date >= {date:Date} - 7
    ),
    returns AS
    (
        SELECT
            c.cohort_date                                AS cohort_date,
            toUInt8(dateDiff('day', c.cohort_date, e.event_date)) AS day_n,
            uniqExact(e.user_id)                         AS retained
        FROM movie_events AS e
        INNER JOIN cohorts AS c ON e.user_id = c.user_id
        WHERE e.event_date BETWEEN {date:Date} - 7 AND {date:Date}
          AND e.event_date >= c.cohort_date
        GROUP BY cohort_date, day_n
    ),
    grid AS
    (
        SELECT
            cohort_date,
            cohort_size,
            arrayJoin(range(toUInt8(least(7, dateDiff('day', cohort_date, {date:Date})) + 1))) AS day_n
        FROM
        (
            SELECT cohort_date, uniqExact(user_id) AS cohort_size
            FROM cohorts
            GROUP BY cohort_date
        )
    )
SELECT
    g.cohort_date,
    g.day_n,
    g.cohort_size,
    r.retained,
    r.retained / g.cohort_size AS rate,
    now64(3, 'UTC')            AS computed_at
FROM grid AS g
LEFT JOIN returns AS r ON g.cohort_date = r.cohort_date AND g.day_n = r.day_n
