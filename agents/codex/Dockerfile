FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
WORKDIR /app/agents/codex/codex-sse

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

ARG CODEX_VERSION=0.159.0
RUN npm install -g "@openai/codex@${CODEX_VERSION}"

RUN uv python install 3.14

# Owned by model: uv builds the SDK inside its source tree when the agent starts.
COPY --from=workspace --chown=model:model pyproject.toml uv.lock /app/
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml /app/sdk/python/
COPY --from=workspace --chown=model:model sdk/python/sse/ /app/sdk/python/sse/
COPY codex-sse/ /app/agents/codex/codex-sse

CMD ["./run.sh"]
