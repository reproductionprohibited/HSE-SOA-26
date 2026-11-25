-- Retention D1 и D7 как скалярные метрики, привязанные к дате когорты.
-- Пишем только для когорт, у которых день N уже наступил (cohort_date + N <= {date}): для более молодых
-- когорт значение ещё неизвестно, и ноль вместо него вводил бы в заблуждение.
INSERT INTO agg_daily_metrics (metric_date, metric_name, value, computed_at)
SELECT
    cohort_date              AS metric_date,
    concat('retention_d', toString(day_n)) AS metric_name,
    rate                     AS value,
    now64(3, 'UTC')          AS computed_at
FROM agg_retention_cohort FINAL
WHERE cohort_date BETWEEN {date:Date} - 7 AND {date:Date}
  AND day_n IN (1, 7)
