FROM python:3.12-slim

ARG GIT_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PALACE_GIT_SHA=$GIT_SHA

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer) without installing the project itself
COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --no-install-project

# Now copy source and install the project package
COPY src/ src/
RUN uv sync --no-dev

CMD ["uv", "run", "uvicorn", "palace_mcp.main:app", "--host", "0.0.0.0", "--port", "8000"]
