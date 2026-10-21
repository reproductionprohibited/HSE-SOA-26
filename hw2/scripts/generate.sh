#!/bin/sh
# Генерация моделей и роутера из OpenAPI-спецификации.
# Используется и локально (make generate), и при сборке Docker-образа.
set -eu

cd "$(dirname "$0")/.."

GEN_DIR=generated/marketplace_api

rm -rf "$GEN_DIR"
uv run --frozen --only-group codegen fastapi-codegen \
    --input openapi/marketplace.yaml \
    --output "$GEN_DIR" \
    --template-dir openapi/templates \
    --output-model-type pydantic_v2.BaseModel \
    --python-version 3.12 \
    --strict-nullable \
    --disable-timestamp
