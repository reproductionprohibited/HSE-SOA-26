--liquibase formatted sql

--changeset hw3:004-seat-reservations
CREATE TABLE seat_reservations (
    id         UUID               PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_id  UUID               NOT NULL REFERENCES flights (id),
    booking_id UUID               NOT NULL,  -- бронирование в Booking Service (другая БД, без FK)
    seat_count INTEGER            NOT NULL,
    status     reservation_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ        NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ        NOT NULL DEFAULT now(),

    -- Одному бронированию соответствует ровно одна резервация
    CONSTRAINT seat_reservations_booking_id_uq   UNIQUE (booking_id),
    CONSTRAINT seat_reservations_seat_count_positive CHECK (seat_count > 0)
);

CREATE INDEX seat_reservations_flight_id_idx ON seat_reservations (flight_id);
--rollback DROP TABLE seat_reservations;
