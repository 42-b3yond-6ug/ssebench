FROM ssebench-agent

# The wrapper depends on the SDK at ../../../sdk/python, so /app mirrors the
# repository layout; the SDK comes from the `sdk` build context.
WORKDIR /app/agents/codex/codex-sse

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g npm@latest

RUN npm install -g @openai/codex

RUN uv python install 3.14

# Owned by model: uv builds the SDK inside its source tree when the agent starts.
COPY --from=sdk --chown=model:model pyproject.toml /app/sdk/python/
COPY --from=sdk --chown=model:model sse/ /app/sdk/python/sse/
COPY codex-sse/ /app/agents/codex/codex-sse

CMD ["./run.sh"]
