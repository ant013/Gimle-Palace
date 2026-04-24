# codebase-memory-mcp sidecar — built from official GitHub release binary.
# Pinned to v0.6.0 with SHA-256 verification of the release tarball.
# Update CM_VERSION + CM_SHA256_AMD64/ARM64 in lockstep when upgrading.
FROM debian:bookworm-slim AS fetch

ARG CM_VERSION=v0.6.0
ARG TARGETARCH=amd64

# Known-good SHA-256 digests from
# https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.6.0/checksums.txt
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

FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 cmm

COPY --from=fetch /tmp/codebase-memory-mcp /usr/local/bin/codebase-memory-mcp

USER cmm
ENV PORT=8765

EXPOSE 8765

ENTRYPOINT ["codebase-memory-mcp"]
CMD ["--skip-config"]
