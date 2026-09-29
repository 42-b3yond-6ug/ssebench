# Stage 1: Install Claude Code (cached separately from agent code changes)
FROM ubuntu:22.04 AS claude-installer
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 model
USER model
ENV HOME=/home/model
ARG CLAUDE_CODE_VERSION=2.1.277
ARG CLAUDE_CODE_SHA256=722210f05ba494d8f6df69423c4d4f2960900f7a007d0532851c7a36e375cab7
# `claude install` sets up the launcher in ~/.local/bin for this version.
RUN curl -fsSLo /tmp/claude \
        "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}/linux-x64/claude" && \
    echo "${CLAUDE_CODE_SHA256}  /tmp/claude" | sha256sum -c - && \
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
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml /app/sdk/python/
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
