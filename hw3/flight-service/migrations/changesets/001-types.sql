--liquibase formatted sql

--changeset hw3:001-flight-status
CREATE TYPE flight_status AS ENUM ('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED');
--rollback DROP TYPE flight_status;

--changeset hw3:001-reservation-status
CREATE TYPE reservation_status AS ENUM ('ACTIVE', 'RELEASED', 'EXPIRED');
--rollback DROP TYPE reservation_status;
