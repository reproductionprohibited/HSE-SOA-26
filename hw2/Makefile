.PHONY: generate up down psql

# Генерация моделей и роутера из OpenAPI-спецификации
generate:
	./scripts/generate.sh

# Сборка (включая кодогенерацию) и запуск всей системы
up:
	docker compose up --build

# Остановка с удалением данных БД
down:
	docker compose down -v

psql:
	docker compose exec db psql -U marketplace -d marketplace
