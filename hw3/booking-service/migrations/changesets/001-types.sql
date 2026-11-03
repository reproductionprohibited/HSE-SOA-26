--liquibase formatted sql

--changeset hw3:001-booking-status
CREATE TYPE booking_status AS ENUM ('CONFIRMED', 'CANCELLED');
--rollback DROP TYPE booking_status;
