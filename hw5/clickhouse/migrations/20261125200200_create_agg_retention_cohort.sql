-- migrate:up
-- Когортный retention: когорта — дата первого VIEW_STARTED пользователя, day_n — день жизни (0..7),
-- retained — сколько пользователей когорты были активны в день cohort_date + day_n.
CREATE TABLE IF NOT EXISTS agg_retention_cohort
(
    cohort_date Date,
    day_n       UInt8,
    cohort_size UInt64,
    retained    UInt64,
    rate        Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (cohort_date, day_n);

-- migrate:down
DROP TABLE IF EXISTS agg_retention_cohort;
