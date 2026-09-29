# Reference agent: applies the task's reference patch. See README.md.
FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
WORKDIR /app
COPY --from=workspace pyproject.toml uv.lock /app/
COPY --from=workspace sdk/python/pyproject.toml /app/sdk/python/
COPY --from=workspace sdk/python/sse/ /app/sdk/python/sse/
COPY reference-sse/pyproject.toml /app/agents/reference/reference-sse/

# The run container cannot reach a package index, so the environment is built
# here, on a Python that the model user can execute (uv's default location is
# under /root).
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/usr/local/bin/uv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_NO_CACHE=1 \
    uv sync --package reference-sse --frozen --no-dev --no-editable

COPY reference-sse/ /app/agents/reference/reference-sse/
WORKDIR /app/agents/reference/reference-sse

CMD ["/app/.venv/bin/python", "main.py"]
