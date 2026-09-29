ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-rust:1.0.0

RUN rustup default nightly-2022-07-11

RUN mkdir -p /src

COPY ./rust-smallvec /src/rust-smallvec

# Make the project a git repo
RUN cd /src/rust-smallvec && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

# Copy harness
COPY ./harness /ssebench/harness

# Upstream commits no lockfile, so the crate versions are pinned here
COPY Cargo.lock /src/rust-smallvec/Cargo.lock
RUN cd /src/rust-smallvec && cargo fetch --locked && cp Cargo.lock /ssebench/harness/Cargo.lock

# Copy config file
COPY sse/config.yaml /ssebench/config.yaml
# Copy interaction scripts
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
RUN chmod +x /ssebench/scripts/build.sh \
    && chmod +x /ssebench/scripts/run.sh \
    && chmod +x /ssebench/scripts/test.sh
# Copy related files
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports
