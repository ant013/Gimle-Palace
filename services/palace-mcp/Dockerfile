FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv sync --no-dev

COPY src/ src/

CMD ["uv", "run", "uvicorn", "palace_mcp.main:app", "--host", "0.0.0.0", "--port", "8000"]
