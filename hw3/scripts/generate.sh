#!/usr/bin/env bash
# Генерация Python-кода (messages, gRPC stubs, .pyi) из proto/ в указанный каталог.
#   Использование: generate.sh <out_dir>
#   Интерпретатор с grpcio-tools берётся из $PYTHON (по умолчанию python).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?usage: generate.sh <out_dir>}"
PYTHON="${PYTHON:-python}"

rm -rf "$OUT"
mkdir -p "$OUT"

find "$ROOT/proto" -name '*.proto' -print0 | xargs -0 "$PYTHON" -m grpc_tools.protoc \
    -I "$ROOT/proto" \
    --python_out="$OUT" \
    --grpc_python_out="$OUT" \
    --pyi_out="$OUT"

echo "generated: $(find "$OUT" -name '*.py' | wc -l | tr -d ' ') python files -> $OUT"
