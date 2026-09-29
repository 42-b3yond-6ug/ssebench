FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
RUN mkdir -p /app/agents/codex/codex-sse && chown -R model:model /app
WORKDIR /app/agents/codex/codex-sse

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

ARG CODEX_VERSION=0.159.0
RUN npm install -g "@openai/codex@${CODEX_VERSION}"

COPY --from=workspace --chown=model:model pyproject.toml uv.lock /app/
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml /app/sdk/python/
COPY --from=workspace --chown=model:model sdk/python/sse/ /app/sdk/python/sse/
COPY --chown=model:model codex-sse/ /app/agents/codex/codex-sse

# Install the wrapper's environment, Python included, now: at run time the
# container reaches the LiteLLM proxy only.
USER model
RUN HOME=/home/model uv sync --frozen --no-dev --package codex-sse
USER root

CMD ["./run.sh"]
