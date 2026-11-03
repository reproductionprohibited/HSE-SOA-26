--liquibase formatted sql

--changeset hw3:002-airports
CREATE TABLE airports (
    code    CHAR(3) PRIMARY KEY,
    name    TEXT    NOT NULL,
    city    TEXT    NOT NULL,
    country TEXT    NOT NULL,

    CONSTRAINT airports_code_iata CHECK (code ~ '^[A-Z]{3}$')
);
--rollback DROP TABLE airports;

--changeset hw3:002-airlines
CREATE TABLE airlines (
    code VARCHAR(3) PRIMARY KEY,
    name TEXT       NOT NULL,

    CONSTRAINT airlines_code_format CHECK (code ~ '^[A-Z0-9]{2,3}$')
);
--rollback DROP TABLE airlines;
