.PHONY: up down logs test lock ch psql migration-new schema-dump

DBMATE_IMAGE := ghcr.io/amacneil/dbmate:2.26.0
NETWORK := hw5_default

# Сборка и запуск всей системы
up:
	docker compose up --build

# Остановка с удалением данных
down:
	docker compose down -v

logs:
	docker compose logs -f movie-service event-generator

# Интеграционный тест: продюсер → Kafka → ClickHouse (система должна быть запущена или поднимется сама)
test:
	docker compose --profile test run --rm --build tests

lock:
	@for d in movie-service aggregation-service tests; do (cd $$d && uv lock) || exit 1; done

ch:
	docker compose exec clickhouse clickhouse-client --user analytics --password analytics --database analytics

psql:
	docker compose exec postgres psql -U analytics -d analytics

# Новая миграция: make migration-new db=ch|pg name=create_something
migration-new:
	@test -n "$(name)" || (echo "usage: make migration-new db=ch|pg name=..." && exit 1)
	docker run --rm -u $$(id -u):$$(id -g) -v $(CURDIR)/$(if $(filter ch,$(db)),clickhouse,postgres)/migrations:/db/migrations \
		$(DBMATE_IMAGE) --migrations-dir /db/migrations new $(name)

# Дамп итоговой схемы обеих БД в clickhouse/schema.sql и postgres/schema.sql (система должна быть запущена)
schema-dump:
	docker run --rm --network $(NETWORK) -v $(CURDIR)/clickhouse:/out \
		-e DATABASE_URL=clickhouse://analytics:analytics@clickhouse:9000/analytics \
		$(DBMATE_IMAGE) --schema-file /out/schema.sql dump
	docker run --rm --network $(NETWORK) -v $(CURDIR)/postgres:/out \
		-e DATABASE_URL="postgres://analytics:analytics@postgres:5432/analytics?sslmode=disable" \
		$(DBMATE_IMAGE) --schema-file /out/schema.sql dump
