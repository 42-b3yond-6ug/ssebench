ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:latest

RUN mkdir /src

RUN git clone https://gitlab.gnome.org/GNOME/libxml2.git /src/libxml2 && \
    cd /src/libxml2 && \
    git checkout 069bcda17d8194e9582c64dd4bc9dac99b015810 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    wget \
    pkg-config \
    autotools-dev \
    automake \
    libtool \
    zlib1g-dev \
    liblzma-dev \
    libicu-dev \
    python3-dev \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3-config /usr/bin/python-config && \
    pip install setuptools --break-system-packages

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
