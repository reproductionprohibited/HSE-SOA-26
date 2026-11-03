#!/bin/sh
# Sentinel переписывает свой конфиг во время работы (кто сейчас мастер, известные реплики),
# поэтому конфиг генерируется в /data, а не монтируется read-only. Если он уже есть
# (рестарт контейнера после failover) — используем его, иначе sentinel снова считал бы
# мастером исходный redis-master.
set -eu

CONF=/data/sentinel.conf

if [ ! -f "$CONF" ]; then
    cat > "$CONF" <<EOF
port 26379
# В Docker без hostname-ов sentinel анонсировал бы внутренние IP контейнеров
sentinel resolve-hostnames yes
sentinel announce-hostnames yes
sentinel announce-ip ${SENTINEL_ANNOUNCE_HOST}
sentinel monitor ${REDIS_MASTER_NAME} ${REDIS_MASTER_HOST} 6379 ${SENTINEL_QUORUM}
sentinel down-after-milliseconds ${REDIS_MASTER_NAME} 5000
sentinel failover-timeout ${REDIS_MASTER_NAME} 10000
sentinel parallel-syncs ${REDIS_MASTER_NAME} 1
EOF
fi

exec redis-server "$CONF" --sentinel
