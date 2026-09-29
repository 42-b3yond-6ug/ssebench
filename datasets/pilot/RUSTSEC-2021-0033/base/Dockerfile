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


# Install Rust toolchain
COPY --from=rust:1.75.0-slim /usr/local/cargo /usr/local/cargo
COPY --from=rust:1.75.0-slim /usr/local/rustup /usr/local/rustup

ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:$PATH

# SSE-Bench Shared Assets (ver 1.0)
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
