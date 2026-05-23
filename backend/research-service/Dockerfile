FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8090

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
