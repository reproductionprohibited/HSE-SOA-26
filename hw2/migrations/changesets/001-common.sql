--liquibase formatted sql

--changeset marketplace:001-set-updated-at-function splitStatements:false
-- Общая триггерная функция: автоматически проставляет updated_at при UPDATE
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--rollback DROP FUNCTION set_updated_at();
