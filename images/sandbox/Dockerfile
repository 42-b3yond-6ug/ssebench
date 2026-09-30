FROM ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv

# The evaluator and the MCP server are members of the uv workspace at the
# repository root. Each venv is synced from a copy of just the workspace files
# it needs, directly at its final location; --no-editable installs the SDK into
# the venv, so /src is not needed at run time.
FROM ubuntu:24.04 AS python-builder
COPY --from=uv /uv /bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY sdk/python/pyproject.toml sdk/python/README.md sdk/python/
COPY sdk/python/sse/ sdk/python/sse/
COPY runtime/evaluator/pyproject.toml runtime/evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/
RUN UV_PROJECT_ENVIRONMENT=/evaluator/.venv \
        uv sync --package ssebench-evaluator --frozen --no-dev --no-editable && \
    UV_PROJECT_ENVIRONMENT=/ssebench/mcp/.venv \
        uv sync --package ssebench-mcp --frozen --no-dev --no-editable
COPY runtime/evaluator/pyproject.toml runtime/evaluator/*.py /evaluator/
COPY runtime/mcp/pyproject.toml runtime/mcp/*.py /ssebench/mcp/

# Plugins: plugins.yaml and the schema always ship, so the entrypoint validates
# them at startup; a venv per plugin is installed only for the plugins this run
# selected (PLUGINS is a space-separated list). Each plugin gets its own venv
# next to its code, like the evaluator; run.sh runs it with that venv's Python.
ARG PLUGINS=""
COPY runtime/plugins/ /src/runtime/plugins/
RUN mkdir -p /plugins && \
    cp /src/runtime/plugins/plugins.yaml /src/runtime/plugins/schema.json /plugins/ && \
    for name in ${PLUGINS}; do \
        cp -r "/src/runtime/plugins/${name}/." "/plugins/${name}/" && \
        UV_PROJECT_ENVIRONMENT="/plugins/${name}/.venv" \
            uv sync --package "ssebench-plugin-${name}" --frozen --no-dev --no-editable && \
        chmod +x "/plugins/${name}/run.sh" ; \
    done


# Only unpacks a download, so it runs on the build platform; TARGETARCH picks the
# build to fetch. To bump OPENCODE_VERSION, update both checksums from the
# release's assets.
FROM --platform=$BUILDPLATFORM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS opencode-downloader
RUN apk add --no-cache wget ca-certificates
ARG TARGETARCH
ARG OPENCODE_VERSION=1.2.10
ARG OPENCODE_SHA256_AMD64=ebcc24012e8f067b10d7416430c88e9c429115ecfbccf8da9eb59db3b629a358
ARG OPENCODE_SHA256_ARM64=d9a9d4f0bc1ed246258c0e8846e80593755a72bf4afd3940c4071d6f0b7b7775
RUN case "${TARGETARCH}" in \
      amd64) asset=x64; sha256="${OPENCODE_SHA256_AMD64}" ;; \
      arm64) asset=arm64; sha256="${OPENCODE_SHA256_ARM64}" ;; \
      *) echo "no opencode release for ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    wget -qO /tmp/opencode.tar.gz \
        "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${asset}.tar.gz" && \
    echo "${sha256}  /tmp/opencode.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/opencode && \
    rm /tmp/opencode.tar.gz


# Both binaries are cross-compiled on the build platform, as in images/runtime,
# so building for another architecture needs no emulation here.
FROM --platform=$BUILDPLATFORM rust:1.98.1-alpine AS daemon-builder
# zig is the C compiler and linker for the musl targets.
RUN apk add --no-cache cargo-zigbuild musl-dev
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      amd64) echo x86_64-unknown-linux-musl ;; \
      arm64) echo aarch64-unknown-linux-musl ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac > /rust-target && \
    rustup target add "$(cat /rust-target)"
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY sdk/daemon/Cargo.toml sdk/daemon/
COPY sdk/daemon/src/ sdk/daemon/src/
RUN target="$(cat /rust-target)" && \
    cargo zigbuild --release --locked --bin ssebench-daemon --target "$target" && \
    cp "target/$target/release/ssebench-daemon" /ssebench-daemon


FROM --platform=$BUILDPLATFORM golang:1.26-bookworm AS entrypoint-builder
COPY runtime/entrypoint/ /build/
WORKDIR /build
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -ldflags="-s -w -X main.version=${VERSION}" -o /entrypoint ./cmd/ssebench-entrypoint


# The daemon and the entrypoint, laid out like the runtime image
# (images/runtime). Passing
#   --build-context runtime=docker-image://<registry>/runtime:<version>
# replaces this stage, and skips both builds above.
FROM scratch AS runtime
COPY --from=daemon-builder /ssebench-daemon /ssebench/ssebench-daemon
COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint


FROM case-image AS case-image-builder

FROM case-image
ARG SOURCE_DIR

# Stash original source as a root-only snapshot, re-populate owned by model (uid 1000)
RUN mv "${SOURCE_DIR}" /ssebench-repo && chmod 700 /ssebench-repo && chmod 700 /ssebench
COPY --from=case-image-builder --chown=1000:1000 ${SOURCE_DIR}/ ${SOURCE_DIR}/

# Create model user, init clean git repo
COPY --chmod=755 images/common/ /tmp/image-setup/
RUN /tmp/image-setup/setup-source.sh "${SOURCE_DIR}" && rm -r /tmp/image-setup

COPY --from=python-builder /root/.local/share/uv/python /root/.local/share/uv/python
COPY --from=python-builder /evaluator /evaluator
COPY --from=python-builder /ssebench/mcp /ssebench/mcp
# Root-owned and not writable by the agent, so a plugin's code cannot be
# tampered with before a grading-phase plugin runs it as root.
COPY --from=python-builder /plugins /plugins
COPY --from=opencode-downloader /usr/local/bin/opencode /usr/local/bin/opencode
COPY --from=runtime /ssebench/ssebench-daemon /ssebench/ssebench-daemon

COPY --from=runtime /usr/local/bin/entrypoint /usr/local/bin/entrypoint
ENTRYPOINT [ "/usr/local/bin/entrypoint" ]
