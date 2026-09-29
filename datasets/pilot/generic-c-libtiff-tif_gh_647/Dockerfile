ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:latest

RUN mkdir /src

RUN git clone https://gitlab.com/libtiff/libtiff.git /src/libtiff && \
    cd /src/libtiff && \
    git checkout b00d0060ba2fb4c0f8bcb4bbb9fe4426ab5457dc && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    autotools-dev \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libzstd-dev \
    zlib1g-dev \
    libjpeg-dev \
    liblzma-dev \
    libwebp-dev \
    libzstd-dev \
    libdeflate-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy config file
COPY sse/config.yaml /ssebench/config.yaml
# Copy interaction scripts
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
# Copy related files
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports
