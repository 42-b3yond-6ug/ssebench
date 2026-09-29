# =============================================================================
# Stage 1: Build entrypoint binary (static Go binary, no runtime deps)
# =============================================================================
FROM golang:1.26-bookworm AS entrypoint-builder

COPY runtime/entrypoint/ /build/
WORKDIR /build
ARG VERSION=dev
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w -X main.version=${VERSION}" -o /entrypoint .


# =============================================================================
# Stage 2: Final image
# =============================================================================
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  curl \
  git \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Create user "model" with uid/gid 1000 for running agents as non-root
# This allows agents to use --dangerously-skip-permissions (requires non-root)
# ubuntu:24.04 already has a user "ubuntu" with uid/gid 1000.
RUN userdel --remove ubuntu && \
    groupadd -g 1000 model && \
    useradd -m -u 1000 -g 1000 -s /bin/bash model

# SSEBench shared assets
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY runtime/evaluator/ /evaluator/
COPY runtime/mcp/ /mcp/

# Copy entrypoint binary (static Go binary, works on any base image)
COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint
ENTRYPOINT [ "/usr/local/bin/entrypoint", "--mode", "sidecar", "--" ]
