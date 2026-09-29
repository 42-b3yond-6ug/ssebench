# The Python projects resolve the SDK as a path relative to their place in the
# repository, so they are synced from a copy of that layout under /src; each
# venv is created directly at its final location.
FROM ubuntu:24.04 AS evaluator-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY sdk/python/pyproject.toml /src/sdk/python/
COPY sdk/python/sse/ /src/sdk/python/sse/
COPY runtime/evaluator/pyproject.toml /src/runtime/evaluator/
COPY runtime/evaluator/pyproject.toml /evaluator/
COPY runtime/evaluator/*.py /evaluator/
RUN cd /src/runtime/evaluator && UV_PROJECT_ENVIRONMENT=/evaluator/.venv uv sync --no-dev


FROM ubuntu:24.04 AS mcp-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY sdk/python/pyproject.toml /src/sdk/python/
COPY sdk/python/sse/ /src/sdk/python/sse/
COPY runtime/mcp/pyproject.toml /src/runtime/mcp/
COPY runtime/mcp/pyproject.toml /ssebench/mcp/
COPY runtime/mcp/*.py /ssebench/mcp/
RUN cd /src/runtime/mcp && UV_PROJECT_ENVIRONMENT=/ssebench/mcp/.venv uv sync --no-dev


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


FROM golang:1.22-bookworm AS entrypoint-builder
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

COPY --from=evaluator-builder /root/.local/share/uv/python /root/.local/share/uv/python
COPY --from=evaluator-builder /evaluator /evaluator
COPY --from=mcp-builder /ssebench/mcp /ssebench/mcp
COPY --from=opencode-downloader /usr/local/bin/opencode /usr/local/bin/opencode
COPY --from=daemon-builder /build/target/release/ssebench-daemon /ssebench/ssebench-daemon

COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint
ENTRYPOINT [ "/usr/local/bin/entrypoint" ]
