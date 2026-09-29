ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:1.0.0

RUN mkdir /src

RUN git clone https://github.com/Exiv2/exiv2.git /src/exiv2 && \
    cd /src/exiv2 && \
    git checkout f05d100579effd7459fd0715b26239d4cd2c9bcc && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    gcc-9 \
    g++-9 \
    libexpat1-dev \
    zlib1g-dev \
    libssh-dev \
    libcurl4-openssl-dev \
    libgtest-dev \
    libinih-dev \
    libxml2-utils \
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
