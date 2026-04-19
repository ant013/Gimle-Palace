# --- builder stage -------------------------------------------------------
FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer) without installing the project itself
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

# Now copy source and install the project package
COPY src/ src/
RUN uv sync --no-dev

# --- runtime stage -------------------------------------------------------
FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286 AS runtime

ARG GIT_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PALACE_GIT_SHA=$GIT_SHA \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

USER appuser

CMD ["uvicorn", "palace_mcp.main:app", "--host", "0.0.0.0", "--port", "8000"]
