ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-rust:1.0.0

# Install and switch to stable (support Rust 2024)
RUN rustup toolchain install stable \
 && rustup default stable \
 && rustup update stable

# Check versions
RUN rustc -V && cargo -V

WORKDIR /src/ammonia

# Make the project a git repo
RUN git clone https://github.com/rust-ammonia/ammonia.git /src/ammonia && \ 
    cd /src/ammonia && \
    git checkout ae3fb569e1f0019a8a9793616d1944614d79e7a0 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

# Copy harness
COPY ./harness /ssebench/harness
RUN cd /ssebench/harness && cargo fetch

RUN cd /src/ammonia && cargo fetch && cp Cargo.lock /ssebench/harness/Cargo.lock

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
