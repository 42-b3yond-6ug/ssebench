ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:latest

RUN mkdir /src

RUN git clone https://github.com/python/cpython.git /src/cpython && \
    cd /src/cpython && \
    git checkout 24c84d816f2f2ecb76b80328c3f1d8c05ead0b10 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    libcurl4-openssl-dev \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libffi-dev \
    libsqlite3-dev \
    libreadline-dev \
    libbz2-dev \
    liblzma-dev \
    libncurses-dev \
    tk-dev \
    libgdbm-dev \
    libdb-dev \
    libnss3-dev \
    libexpat1-dev \
    libzstd-dev \
    uuid-dev \
    xvfb && \
    rm -rf /var/lib/apt/lists/*

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
