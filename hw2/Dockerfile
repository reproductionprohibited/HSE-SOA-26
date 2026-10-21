FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./


# ---------- 1. Кодогенерация из OpenAPI ----------
FROM base AS codegen
RUN uv sync --frozen --only-group codegen
COPY scripts/generate.sh scripts/
COPY openapi/ openapi/
RUN ./scripts/generate.sh


# ---------- 2. Runtime ----------
FROM base AS runtime
RUN uv sync --frozen --no-dev
COPY --from=codegen /app/generated/ generated/
COPY openapi/marketplace.yaml openapi/
COPY app/ app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:/app/generated" \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
