FROM ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 AS uv

# The runtime of the agent container in sidecar mode: the entrypoint, the MCP
# server and the evaluator. It holds no task files; the project's source tree
# and the daemon's sockets are shared from the task container at run time.

# The evaluator and the MCP server are members of the uv workspace at the
# repository root. Each venv is synced from a copy of just the workspace files
# it needs, directly at its final location; --no-editable installs the SDK into
# the venv, so /src is not needed at run time.
FROM ubuntu:26.04 AS python-builder
COPY --from=uv /uv /bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml sdk/python/README.md sdk/python/
COPY sdk/python/sse/ sdk/python/sse/
COPY runtime/evaluator/pyproject.toml runtime/evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/
RUN UV_PROJECT_ENVIRONMENT=/evaluator/.venv \
        uv sync --package ssebench-evaluator --frozen --no-dev --no-editable && \
    UV_PROJECT_ENVIRONMENT=/mcp/.venv \
        uv sync --package ssebench-mcp --frozen --no-dev --no-editable
COPY runtime/evaluator/pyproject.toml runtime/evaluator/*.py /evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/*.py /mcp/


# Cross-compiled on the build platform, as in images/runtime, so building for
# another architecture needs no emulation here.
FROM --platform=$BUILDPLATFORM golang:1.27-bookworm AS entrypoint-builder
COPY runtime/entrypoint/ /build/
WORKDIR /build
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -ldflags="-s -w -X main.version=${VERSION}" -o /entrypoint ./cmd/ssebench-entrypoint


# The entrypoint, laid out like the runtime image (images/runtime). Passing
#   --build-context runtime=docker-image://<registry>/runtime:<version>
# replaces this stage, and skips the build above.
FROM scratch AS runtime
COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint


FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Agents run as the non-root user "model" (uid/gid 1000), which owns the shared
# source tree. The ubuntu image already has a user "ubuntu" with uid/gid 1000.
RUN userdel --remove ubuntu && \
    groupadd -g 1000 model && \
    useradd -m -u 1000 -g 1000 -s /bin/bash model && \
    su model -c "git config --global user.name 'SSEBench Agent' && git config --global user.email 'agent@ssebench.invalid'"

COPY --from=uv /uv /uvx /bin/
COPY --from=python-builder /root/.local/share/uv/python /root/.local/share/uv/python
COPY --from=python-builder /evaluator /evaluator
COPY --from=python-builder /mcp /mcp

COPY --from=runtime /usr/local/bin/entrypoint /usr/local/bin/entrypoint
ENTRYPOINT [ "/usr/local/bin/entrypoint", "--mode", "sidecar", "--" ]
