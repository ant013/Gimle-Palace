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

# ML heavy packages in an isolated layer.
# Docker layer cache: invalidated only when constraints/ml-packages.txt changes.
# A non-ML dep change in pyproject.toml will NOT trigger this layer.
# uv cache mount: packages survive layer cache miss — no PyPI re-download.
# torch ~430MB (arm64) / ~530MB (x86_64): first build on a clean host takes 5-15 min.
# Scratch rebuild: docker buildx build --no-cache --build-arg GIT_SHA=$(git rev-parse HEAD) .
COPY constraints/ml-packages.txt ./constraints/ml-packages.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    echo "[BUILD ml-deps] Installing ML stack (torch, sentence-transformers) — first build may take 5-15 min" && \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv -r constraints/ml-packages.txt && \
    echo "[BUILD ml-deps] done"

# All production dependencies (frozen lockfile).
# Layer cache: invalidated only when pyproject.toml or uv.lock changes.
# uv sync --frozen enforces the committed lockfile exactly; any drift is a build error.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    echo "[BUILD deps] Syncing all deps from frozen lockfile..." && \
    uv sync --frozen --no-dev --no-install-project && \
    echo "[BUILD deps] done"

# Install the project package (source layer).
# Layer cache: invalidated only when src/ changes.
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    echo "[BUILD project] Installing palace-mcp from source..." && \
    uv sync --frozen --no-dev && \
    echo "[BUILD project] done"

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

RUN adduser --disabled-password --gecos "" --uid 1000 appuser && \
    mkdir -p /home/appuser/.cache/codebase-memory-mcp && \
    chown -R appuser:appuser /home/appuser/.cache && \
    mkdir -p /var/lib/palace/tantivy && \
    chown -R appuser:appuser /var/lib/palace && \
    mkdir -p /data/hf-cache && \
    chown -R appuser:appuser /data
# Pre-create /data/hf-cache owned by appuser so a fresh `palace-hf-cache`
# named volume inherits 1000:1000 instead of being created as root and
# blocking Qodo model downloads (GIM-945). Docker copies the image's
# mount-point ownership into a fresh anonymous/named volume on first
# attach; existing volumes still need a one-off `chown -R appuser:appuser
# /data/hf-cache` (see services/palace-mcp/README.md).

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=cm-fetch /tmp/codebase-memory-mcp /usr/local/bin/codebase-memory-mcp

# Entrypoint checks Tantivy volume ownership before starting (GIM-101a T10 — Architect F19)
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Image smoke check script — run after build to verify pins and local-only mode
COPY scripts/smoke_image.py /app/scripts/smoke_image.py

USER appuser

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "palace_mcp.main:app", "--host", "0.0.0.0", "--port", "8000"]
