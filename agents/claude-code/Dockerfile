# Stage 1: Install Claude Code (cached separately from agent code changes)
FROM ubuntu:22.04 AS claude-installer
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 model
USER model
ENV HOME=/home/model
ARG TARGETARCH
ARG CLAUDE_CODE_VERSION=2.1.285
# Checksums of the linux-x64 and linux-arm64 builds, from the release's
# manifest.json; update both when bumping the version.
ARG CLAUDE_CODE_SHA256_AMD64=33dad1ec615a2e08cc78b494f05c110e49916de2c79d78ec8799ebf46b233d29
ARG CLAUDE_CODE_SHA256_ARM64=24fac77749bed3d91365d6b6915aa4b824e14318ecb6bc17adbc192f01c9173d
# `claude install` sets up the launcher in ~/.local/bin for this version.
RUN case "${TARGETARCH}" in \
      amd64) platform=linux-x64; sha256="${CLAUDE_CODE_SHA256_AMD64}" ;; \
      arm64) platform=linux-arm64; sha256="${CLAUDE_CODE_SHA256_ARM64}" ;; \
      *) echo "no Claude Code release for ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    curl -fsSLo /tmp/claude \
        "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}/${platform}/claude" && \
    echo "${sha256}  /tmp/claude" | sha256sum -c - && \
    chmod +x /tmp/claude && \
    /tmp/claude install "${CLAUDE_CODE_VERSION}" && \
    rm /tmp/claude

# Stage 2: Final image
FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
# Create /app owned by model user (WORKDIR creates as root)
RUN mkdir -p /app/agents/claude-code/claude-code-sse && chown -R model:model /app
WORKDIR /app/agents/claude-code/claude-code-sse

# Copy Claude Code installation from stage 1
COPY --from=claude-installer --chown=model:model /home/model/.local /home/model/.local
COPY --from=claude-installer --chown=model:model /home/model/.claude /home/model/.claude

# Ensure model user's home and cache directories have correct ownership
# This prevents "Permission denied" errors when uv runs as model user
RUN mkdir -p /home/model/.cache && \
    rm -rf /home/model/.cache/uv && \
    chown -R model:model /home/model

# Only set CLAUDE path - HOME is set by entrypoint when running as model user
# Setting HOME globally causes MCP server (running as root) to pollute model's cache
ENV CLAUDE=/home/model/.local/bin/claude

COPY --from=workspace --chown=model:model pyproject.toml uv.lock /app/
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml sdk/python/README.md /app/sdk/python/
COPY --from=workspace --chown=model:model sdk/python/sse/ /app/sdk/python/sse/

# Copy agent code (changes frequently, but doesn't invalidate cached stages above)
# .dockerignore excludes .venv, __pycache__, etc.
COPY --chown=model:model claude-code-sse/ /app/agents/claude-code/claude-code-sse

# Install the wrapper's environment, Python included, now: at run time the
# container reaches the LiteLLM proxy only.
USER model
RUN HOME=/home/model uv sync --frozen --no-dev --package claude-code-sse
USER root

CMD ["./run.sh"]
