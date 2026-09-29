# Stage 1: Install Claude Code (cached separately from agent code changes)
FROM ubuntu:22.04 AS claude-installer
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 model
USER model
ENV HOME=/home/model
RUN curl -fsSL https://claude.ai/install.sh | bash

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

# Owned by model: uv creates /app/.venv and builds the SDK inside its source
# tree when the agent starts.
COPY --from=workspace --chown=model:model pyproject.toml uv.lock /app/
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml /app/sdk/python/
COPY --from=workspace --chown=model:model sdk/python/sse/ /app/sdk/python/sse/

# Copy agent code (changes frequently, but doesn't invalidate cached stages above)
# .dockerignore excludes .venv, __pycache__, etc.
COPY --chown=model:model claude-code-sse/ /app/agents/claude-code/claude-code-sse

CMD ["./run.sh"]
