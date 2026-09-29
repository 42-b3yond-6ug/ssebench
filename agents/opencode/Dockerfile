# OpenCode agent — uses the server already installed in ssebench-agent base image.
# The entrypoint starts the OpenCode server; this agent acts as an HTTP client.
FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
RUN mkdir -p /app/agents/opencode/opencode-sse && chown -R model:model /app
WORKDIR /app/agents/opencode/opencode-sse

# Ensure model user's home and cache directories have correct ownership
RUN mkdir -p /home/model/.cache && \
    rm -rf /home/model/.cache/uv && \
    chown -R model:model /home/model

COPY --from=workspace --chown=model:model pyproject.toml uv.lock /app/
COPY --from=workspace --chown=model:model sdk/python/pyproject.toml sdk/python/README.md /app/sdk/python/
COPY --from=workspace --chown=model:model sdk/python/sse/ /app/sdk/python/sse/
COPY --chown=model:model opencode-sse/ /app/agents/opencode/opencode-sse

# Install the wrapper's environment, Python included, now: at run time the
# container reaches the LiteLLM proxy only.
USER model
RUN HOME=/home/model uv sync --frozen --no-dev --package opencode-sse
USER root

CMD ["./run.sh"]
