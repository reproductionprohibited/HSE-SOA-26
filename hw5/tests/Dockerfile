FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /tests

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY *.py ./

ENV PATH="/tests/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["pytest"]
