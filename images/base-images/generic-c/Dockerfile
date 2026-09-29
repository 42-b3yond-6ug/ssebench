FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS ccache-dl
ARG TARGETARCH
RUN apk add --no-cache curl xz && \
    version=4.12.3 && \
    case "${TARGETARCH}" in \
      amd64) arch=x86_64; sha256=a99aa455873c978f6905f07e3176cfdf48bb610990c23ce0e1b718da0f38faa7 ;; \
      arm64) arch=aarch64; sha256=3ac9c7dc17414aa3b731a8c3bf9a3f785153048efbb597656e2827edb5eac936 ;; \
      *) echo "no ccache release for ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/ccache.tar.xz \
      "https://github.com/ccache/ccache/releases/download/v${version}/ccache-${version}-linux-${arch}.tar.xz" && \
    echo "${sha256}  /tmp/ccache.tar.xz" | sha256sum -c - && \
    tar -xJf /tmp/ccache.tar.xz --strip-components=1 -C /tmp "ccache-${version}-linux-${arch}/ccache"

FROM ubuntu:noble-20260911@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3
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
COPY --from=ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 /uv /uvx /bin/
