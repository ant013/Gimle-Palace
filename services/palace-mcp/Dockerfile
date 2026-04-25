# --- cm-fetch stage -------------------------------------------------------
# Pinned to v0.6.0 with SHA-256 verification of the release tarball.
# Update CM_VERSION + CM_SHA256_* in lockstep when upgrading.
FROM debian:bookworm-slim@sha256:f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252 AS cm-fetch

ARG CM_VERSION=v0.6.0
ARG TARGETARCH=amd64
ARG CM_SHA256_AMD64=68dfebf041b37f4b64bd47a3b56373aeabf3f56f3cbba86de3564bfde9a1b3d5
ARG CM_SHA256_ARM64=b60d567353e64c10f044e4dc408ab1398f56f9930ce394f31fa2ace12a11e1a6

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN set -ex; \
    ARCH="${TARGETARCH}"; \
    URL="https://github.com/DeusData/codebase-memory-mcp/releases/download/${CM_VERSION}/codebase-memory-mcp-linux-${ARCH}-portable.tar.gz"; \
    if [ "$ARCH" = "amd64" ]; then EXPECTED="${CM_SHA256_AMD64}"; \
    elif [ "$ARCH" = "arm64" ]; then EXPECTED="${CM_SHA256_ARM64}"; \
    else echo "Unsupported arch: $ARCH" && exit 1; fi; \
    curl -fsSL "$URL" -o /tmp/cm.tar.gz; \
    echo "${EXPECTED}  /tmp/cm.tar.gz" | sha256sum --check --strict -; \
    tar -xzf /tmp/cm.tar.gz -C /tmp; \
    chmod +x /tmp/codebase-memory-mcp

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

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" appuser && \
    mkdir -p /home/appuser/.cache/codebase-memory-mcp && \
    chown -R appuser:appuser /home/appuser/.cache

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=cm-fetch /tmp/codebase-memory-mcp /usr/local/bin/codebase-memory-mcp

USER appuser

CMD ["uvicorn", "palace_mcp.main:app", "--host", "0.0.0.0", "--port", "8000"]
