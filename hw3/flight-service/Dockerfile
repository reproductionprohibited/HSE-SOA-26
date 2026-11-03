# Build context — hw3/ (нужен общий каталог proto/)
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY flight-service/pyproject.toml flight-service/uv.lock ./


# ---------- 1. Кодогенерация из .proto ----------
FROM base AS codegen
RUN uv sync --frozen --only-group codegen
COPY scripts/generate.sh scripts/
COPY proto/ proto/
RUN PYTHON=/app/.venv/bin/python ./scripts/generate.sh generated


# ---------- 2. Runtime ----------
FROM base AS runtime
RUN uv sync --frozen --no-dev
COPY --from=codegen /app/generated/ generated/
COPY flight-service/app/ app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:/app/generated" \
    PYTHONUNBUFFERED=1

EXPOSE 50051
CMD ["python", "-m", "app.main"]
