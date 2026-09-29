# OpenCode agent — uses the server already installed in ssebench-agent base image.
# The entrypoint starts the OpenCode server; this agent acts as an HTTP client.
FROM ssebench-agent

# The wrapper depends on the SDK at ../../../sdk/python, so /app mirrors the
# repository layout; the SDK comes from the `sdk` build context.
RUN mkdir -p /app/agents/opencode/opencode-sse && chown -R model:model /app
WORKDIR /app/agents/opencode/opencode-sse

# Ensure model user's home and cache directories have correct ownership
RUN mkdir -p /home/model/.cache && \
    rm -rf /home/model/.cache/uv && \
    chown -R model:model /home/model

# Owned by model: uv builds the SDK inside its source tree when the agent starts.
COPY --from=sdk --chown=model:model pyproject.toml /app/sdk/python/
COPY --from=sdk --chown=model:model sse/ /app/sdk/python/sse/
COPY --chown=model:model opencode-sse/ /app/agents/opencode/opencode-sse

CMD ["./run.sh"]
