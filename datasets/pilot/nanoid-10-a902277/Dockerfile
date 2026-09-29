ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-rust:1.0.0

WORKDIR /src/nano-id

# Make the project a git repo
RUN git clone https://github.com/viz-rs/nano-id.git /src/nano-id &&\
    cd /src/nano-id && \
    git checkout d8d2113aa68095ca129c32276ea883ca6324cdc5 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

# Copy harness
COPY ./harness /ssebench/harness

# Upstream commits no lockfile, so the crate versions are pinned here
COPY Cargo.lock /src/nano-id/Cargo.lock
RUN cd /src/nano-id && cargo fetch --locked && cp Cargo.lock /ssebench/harness/Cargo.lock

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

RUN chmod +x /ssebench/scripts/*.sh
