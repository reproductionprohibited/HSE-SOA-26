.PHONY: up down logs generate lock smoke smoke2 smoke3 demo-race demo-auth demo-cache demo-compensation \
	demo-retry demo-sentinel demo-cb psql-flights psql-bookings redis-cli sentinel-cli

SERVICES := flight-service booking-service

# Сборка (включая кодогенерацию из .proto) и запуск всей системы
up:
	docker compose up --build

# Остановка с удалением данных обеих БД
down:
	docker compose down -v

logs:
	docker compose logs -f flight-service booking-service

# Локальная кодогенерация в <service>/generated — для IDE и запуска вне Docker
generate:
	@for svc in $(SERVICES); do \
		(cd $$svc && uv sync --group codegen -q && PYTHON=.venv/bin/python ../scripts/generate.sh generated) || exit 1; \
	done

lock:
	@for svc in $(SERVICES); do (cd $$svc && uv lock) || exit 1; done

psql-flights:
	docker compose exec flights-db psql -U flights -d flights

psql-bookings:
	docker compose exec bookings-db psql -U bookings -d bookings

# redis-cli к текущему мастеру (после failover это может быть redis-replica)
redis-cli:
	docker compose exec redis-sentinel-1 sh -c \
		'redis-cli -h "$$(redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster | head -1)"'

sentinel-cli:
	docker compose exec redis-sentinel-1 redis-cli -p 26379
