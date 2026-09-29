# SSEBench SDK Integration Test Dockerfile
# Multi-stage build: Rust daemon + Python SDK + Test case + Mock Agent

# =============================================================================
# Stage 1: Build Rust daemon
# =============================================================================
FROM rust:1.98.1-alpine AS rust-builder

RUN apk add --no-cache musl-dev

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY sdk/daemon/Cargo.toml sdk/daemon/
COPY sdk/daemon/src/ sdk/daemon/src/

RUN cargo build --release --locked --bin ssebench-daemon

# =============================================================================
# Stage 2: Build Python wheel
# =============================================================================
FROM python:3.12-alpine AS python-builder

WORKDIR /build
COPY sdk/python/pyproject.toml sdk/python/README.md ./
COPY sdk/python/sse/ ./sse/

RUN pip wheel . --no-deps -w dist/

# =============================================================================
# Stage 3: Final integration test image
# =============================================================================
FROM golang:1.21-alpine

# Install Python, git, and other dependencies
RUN apk add --no-cache python3 py3-pip bash git shadow

# Create user "model" with uid/gid 1000 for running agents as non-root
# This mimics the sandbox tool layer setup
RUN addgroup -g 1000 model && \
    adduser -D -u 1000 -G model -s /bin/bash model

# Ensure model user has a proper home directory
RUN mkdir -p /home/model && chown -R model:model /home/model

# Install Rust daemon
COPY --from=rust-builder /build/target/release/ssebench-daemon /usr/local/bin/
RUN chmod +x /usr/local/bin/ssebench-daemon

# Install Python SDK and dependencies
COPY --from=python-builder /build/dist/*.whl /tmp/
RUN pip install --break-system-packages /tmp/*.whl requests-unixsocket

# Create ssebench directory structure (including log directory for agent dialog)
RUN mkdir -p /ssebench/scripts /ssebench/pocs /ssebench/diffs /ssebench/reports /ssebench/log /src/buggy /archive

# Set archive directory for prepare_grading / final_diff endpoints
ENV SSE_ARCHIVE=/archive

# Copy test fixtures: config
COPY sdk/tests/integration/fixtures/config.yaml /ssebench/config.yaml

# Copy test fixtures: buggy source code
COPY sdk/tests/integration/fixtures/source/ /src/buggy/

# Make source folder owned by model user (uid 1000) so bash tool can write
RUN chown -R model:model /src/buggy /archive

# Initialize git repo in source folder (required for /diff and /files endpoints)
# This mimics the real SSEBench setup where source has an initial "buggy commit"
RUN cd /src/buggy && \
    su -c 'git init && \
    git config user.email "test@ssebench.local" && \
    git config user.name "SSEBench Test" && \
    git add . && \
    git commit -m "buggy commit"' model

# Mark source folder as safe for git (daemon runs as root, repo owned by model)
RUN git config --global --add safe.directory /src/buggy

# Create /ssebench-repo: a clean copy of the original repo with vendor/cache intact.
# This mirrors the real SSEBench container infrastructure where /ssebench-repo is
# a pre-populated clone of the original buggy state. The agent's patch is applied
# here during grading instead of destructively cleaning the live source folder.
RUN cp -r /src/buggy /ssebench-repo && \
    chown -R model:model /ssebench-repo && \
    git config --global --add safe.directory /ssebench-repo

# Copy test fixtures: scripts
COPY sdk/tests/integration/fixtures/scripts/ /ssebench/scripts/
RUN chmod +x /ssebench/scripts/*.sh

# Copy test fixtures: PoC, diffs, reports
COPY sdk/tests/integration/fixtures/pocs/ /ssebench/pocs/
COPY sdk/tests/integration/fixtures/diffs/ /ssebench/diffs/
COPY sdk/tests/integration/fixtures/reports/ /ssebench/reports/

# Copy integration test script
COPY sdk/tests/integration/test_sdk.py /test_sdk.py

# Copy mock agent script for dialog testing
COPY sdk/tests/integration/mock_agent.py /mock_agent.py
RUN chmod +x /mock_agent.py

WORKDIR /ssebench

# Default command: run the integration test
CMD ["python3", "/test_sdk.py"]
