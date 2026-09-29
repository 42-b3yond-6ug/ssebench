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
RUN ln -s /usr/local/go/bin/go /usr/local/bin/go && \
    ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt

# SSE-Bench Shared Assets (ver 1.0)
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
