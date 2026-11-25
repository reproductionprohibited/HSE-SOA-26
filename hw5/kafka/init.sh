#!/usr/bin/env bash
# Одноразовая инициализация Kafka: топик movie-events + регистрация Avro-схемы в Schema Registry.
# Идемпотентно: повторный запуск не создаёт дублей (--if-not-exists, повторная регистрация той же схемы
# возвращает ту же версию).
#
# Ключ партиционирования — user_id:
#   - все события одного пользователя (а значит, и одной сессии) попадают в одну партицию, порядок
#     VIEW_STARTED → PAUSED → RESUMED → FINISHED сохраняется — на нём держатся конверсия, время просмотра
#     и retention, которые считаются «по пользователю»;
#   - movie_id дал бы перекос: популярный фильм = горячая партиция; пользователей намного больше, чем фильмов;
#   - порядок событий одного фильма нашим метрикам не нужен.
set -euo pipefail

: "${KAFKA_BOOTSTRAP_SERVERS:?}"
: "${SCHEMA_REGISTRY_URL:?}"
TOPIC="${TOPIC:-movie-events}"
PARTITIONS="${PARTITIONS:-3}"
REPLICATION_FACTOR="${REPLICATION_FACTOR:-1}"
MIN_INSYNC_REPLICAS="${MIN_INSYNC_REPLICAS:-1}"
SCHEMA_FILE="${SCHEMA_FILE:-/schemas/movie_event.avsc}"
SUBJECT="${TOPIC}-value"

echo "[kafka-init] creating topic ${TOPIC}: partitions=${PARTITIONS} rf=${REPLICATION_FACTOR} min.isr=${MIN_INSYNC_REPLICAS}"
kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --create --if-not-exists \
  --topic "$TOPIC" \
  --partitions "$PARTITIONS" \
  --replication-factor "$REPLICATION_FACTOR" \
  --config "min.insync.replicas=${MIN_INSYNC_REPLICAS}"
kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" --describe --topic "$TOPIC"

# Схема передаётся в Registry строкой внутри JSON: сжимаем файл в одну строку и экранируем кавычки.
schema_escaped=$(tr -d '\n' < "$SCHEMA_FILE" | sed 's/\\/\\\\/g; s/"/\\"/g')
payload="{\"schemaType\":\"AVRO\",\"schema\":\"${schema_escaped}\"}"

echo "[kafka-init] setting compatibility BACKWARD for subject ${SUBJECT}"
curl -fsS -X PUT -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"compatibility":"BACKWARD"}' "${SCHEMA_REGISTRY_URL}/config/${SUBJECT}"
echo

echo "[kafka-init] registering schema ${SCHEMA_FILE} under ${SUBJECT}"
registered=$(curl -fsS -X POST -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data "$payload" "${SCHEMA_REGISTRY_URL}/subjects/${SUBJECT}/versions")
echo "[kafka-init] registered: ${registered}"

# Ответ на регистрацию содержит только id; версию берём из lookup по той же схеме.
lookup=$(curl -fsS -X POST -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data "$payload" "${SCHEMA_REGISTRY_URL}/subjects/${SUBJECT}")
echo "[kafka-init] subject=${SUBJECT} $(echo "$lookup" | grep -o '"id":[0-9]*') $(echo "$lookup" | grep -o '"version":[0-9]*')"
echo "[kafka-init] done"
