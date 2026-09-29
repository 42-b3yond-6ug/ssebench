# The evaluator and the MCP server are members of the uv workspace at the
# repository root. Each venv is synced from a copy of just the workspace files
# it needs, directly at its final location; --no-editable installs the SDK into
# the venv, so /src is not needed at run time.
FROM ubuntu:24.04 AS python-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml sdk/python/
COPY sdk/python/sse/ sdk/python/sse/
COPY runtime/evaluator/pyproject.toml runtime/evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/
RUN UV_PROJECT_ENVIRONMENT=/evaluator/.venv \
        uv sync --package ssebench-evaluator --frozen --no-dev --no-editable && \
    UV_PROJECT_ENVIRONMENT=/ssebench/mcp/.venv \
        uv sync --package ssebench-mcp --frozen --no-dev --no-editable
COPY runtime/evaluator/pyproject.toml runtime/evaluator/*.py /evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/*.py /ssebench/mcp/


FROM alpine AS opencode-downloader
RUN apk add --no-cache wget ca-certificates
ARG OPENCODE_VERSION=1.2.10
RUN wget -qO /tmp/opencode.tar.gz \
        "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" && \
    tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/opencode && \
    rm /tmp/opencode.tar.gz


FROM rust:1.98.1-alpine AS daemon-builder
RUN apk add --no-cache musl-dev
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY sdk/daemon/Cargo.toml sdk/daemon/
COPY sdk/daemon/src/ sdk/daemon/src/
RUN cargo build --release --locked --bin ssebench-daemon


FROM golang:1.26-bookworm AS entrypoint-builder
COPY runtime/entrypoint/ /build/
WORKDIR /build
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /entrypoint .


FROM case-image AS case-image-builder

FROM case-image
ARG SOURCE_DIR

# Stash original source as a root-only snapshot, re-populate owned by model (uid 1000)
RUN mv "${SOURCE_DIR}" /ssebench-repo && chmod 700 /ssebench-repo && chmod 700 /ssebench
COPY --from=case-image-builder --chown=1000:1000 ${SOURCE_DIR}/ ${SOURCE_DIR}/

# Create model user, init clean git repo
COPY --chmod=755 images/common/setup-source.sh /tmp/setup-source.sh
RUN /tmp/setup-source.sh "${SOURCE_DIR}" && rm /tmp/setup-source.sh

COPY --from=python-builder /root/.local/share/uv/python /root/.local/share/uv/python
COPY --from=python-builder /evaluator /evaluator
COPY --from=python-builder /ssebench/mcp /ssebench/mcp
COPY --from=opencode-downloader /usr/local/bin/opencode /usr/local/bin/opencode
COPY --from=daemon-builder /build/target/release/ssebench-daemon /ssebench/ssebench-daemon

COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint
ENTRYPOINT [ "/usr/local/bin/entrypoint" ]
