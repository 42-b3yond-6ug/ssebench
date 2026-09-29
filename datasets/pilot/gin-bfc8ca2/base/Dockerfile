FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  build-essential \
  curl \
  ca-certificates \
  git \
  make \
  patch \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*
COPY --from=golang:1.22-bookworm /usr/local/go /usr/local/go
ENV GOROOT=/usr/local/go
ENV GOPATH=/go
ENV PATH="$GOROOT/bin:$GOPATH/bin:$PATH"

# SSE-Bench Shared Assets (ver 1.0)
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/