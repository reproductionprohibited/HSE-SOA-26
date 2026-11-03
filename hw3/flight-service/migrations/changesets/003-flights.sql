--liquibase formatted sql

--changeset hw3:003-flights
-- Номер рейса хранится как airline_code + flight_no ("SU" + 1234 = "SU1234"):
-- строка "SU1234" целиком сама определяла бы авиакомпанию (транзитивная зависимость).
CREATE TABLE flights (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    airline_code    VARCHAR(3)    NOT NULL REFERENCES airlines (code),
    flight_no       INTEGER       NOT NULL,
    origin          CHAR(3)       NOT NULL REFERENCES airports (code),
    destination     CHAR(3)       NOT NULL REFERENCES airports (code),
    departure_time  TIMESTAMPTZ   NOT NULL,
    arrival_time    TIMESTAMPTZ   NOT NULL,
    total_seats     INTEGER       NOT NULL,
    available_seats INTEGER       NOT NULL,
    price           BIGINT        NOT NULL,  -- копейки за одно место
    status          flight_status NOT NULL DEFAULT 'SCHEDULED',
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT flights_flight_no_range           CHECK (flight_no BETWEEN 1 AND 9999),
    CONSTRAINT flights_total_seats_positive      CHECK (total_seats > 0),
    CONSTRAINT flights_available_seats_range     CHECK (available_seats >= 0 AND available_seats <= total_seats),
    CONSTRAINT flights_price_positive            CHECK (price > 0),
    CONSTRAINT flights_arrival_after_departure   CHECK (arrival_time > departure_time),
    CONSTRAINT flights_distinct_airports         CHECK (origin <> destination)
);

-- Номер рейса + дата вылета (UTC) уникальны: SU1234 на 2026-12-01 — один конкретный рейс
CREATE UNIQUE INDEX flights_number_departure_date_uq
    ON flights (airline_code, flight_no, ((departure_time AT TIME ZONE 'UTC')::date));

-- SearchFlights: маршрут + диапазон времени вылета
CREATE INDEX flights_route_departure_idx ON flights (origin, destination, departure_time);
--rollback DROP TABLE flights;
