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


# Install Rust toolchain
COPY --from=rust:1.75.0-slim-bookworm@sha256:70c2a016184099262fd7cee46f3d35fec3568c45c62f87e37f7f665f766b1f74 /usr/local/cargo /usr/local/cargo
COPY --from=rust:1.75.0-slim-bookworm@sha256:70c2a016184099262fd7cee46f3d35fec3568c45c62f87e37f7f665f766b1f74 /usr/local/rustup /usr/local/rustup

ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:$PATH

# SSE-Bench Shared Assets (ver 1.0)
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 /uv /uvx /bin/
