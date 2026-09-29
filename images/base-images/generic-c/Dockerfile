FROM alpine AS ccache-dl
RUN apk add --no-cache curl xz && \
    curl -L https://github.com/ccache/ccache/releases/download/v4.12.3/ccache-4.12.3-linux-x86_64.tar.xz \
    | tar -xJ --strip-components=1 -C /tmp ccache-4.12.3-linux-x86_64/ccache

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  autoconf \
  automake \
  build-essential \
  clang \
  clangd \
  cmake \
  curl \
  gdb \
  git \
  libclang-rt-dev \
  lld \
  llvm \
  make \
  pkg-config \
  python3 \
  python3-pip \
  python3.12-venv \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# ccache setup for faster C/C++ builds
COPY --from=ccache-dl /tmp/ccache /usr/local/bin/ccache
RUN ln -s /usr/local/bin/ccache /usr/local/bin/clang && \
    ln -s /usr/local/bin/ccache /usr/local/bin/clang++
ENV CCACHE_BASEDIR=/ \
    CCACHE_NOHASHDIR=1 \
    CCACHE_DIR=/tmp/ccache
RUN mkdir -p /tmp/ccache && chmod 1777 /tmp/ccache

# SSE-Bench Shared Assets (ver 1.0)
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
