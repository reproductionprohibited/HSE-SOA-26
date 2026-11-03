--liquibase formatted sql

--changeset hw3:002-bookings
CREATE TABLE bookings (
    -- ID генерирует Booking Service до вызова ReserveSeats: он же booking_id резервации
    id              UUID           PRIMARY KEY,
    user_id         UUID           NOT NULL,
    flight_id       UUID           NOT NULL,  -- рейс в Flight Service (другая БД, без FK)
    passenger_name  TEXT           NOT NULL,
    passenger_email TEXT           NOT NULL,
    seat_count      INTEGER        NOT NULL,
    total_price     BIGINT         NOT NULL,  -- копейки, snapshot seat_count * price на момент бронирования
    status          booking_status NOT NULL DEFAULT 'CONFIRMED',
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),

    CONSTRAINT bookings_passenger_name_not_blank CHECK (length(btrim(passenger_name)) > 0),
    CONSTRAINT bookings_passenger_email_format   CHECK (passenger_email ~ '^[^@\s]+@[^@\s]+$'),
    CONSTRAINT bookings_seat_count_positive      CHECK (seat_count > 0),
    CONSTRAINT bookings_total_price_positive     CHECK (total_price > 0)
);

-- GET /bookings?user_id=X, новые сверху
CREATE INDEX bookings_user_id_created_at_idx ON bookings (user_id, created_at DESC);
--rollback DROP TABLE bookings;
