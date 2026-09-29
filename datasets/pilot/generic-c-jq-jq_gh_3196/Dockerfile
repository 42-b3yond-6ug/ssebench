ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:1.0.0

RUN mkdir /src

RUN git clone https://github.com/jqlang/jq.git /src/jq && \
    cd /src/jq && \
    git checkout 64bd8ba3749fe473b0708f999e088dfa94d37a2c && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    libtool \
    make \
    automake \
    autoconf \
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
