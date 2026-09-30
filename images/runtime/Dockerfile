# The static ssebench-daemon and the container entrypoint, at the paths the
# tool layers install them to. Other images copy them from here:
#
#   COPY --from=ghcr.io/42-b3yond-6ug/ssebench/runtime:<version> \
#        /ssebench/ssebench-daemon /ssebench/ssebench-daemon
#
# Build from the repository root:
#   docker buildx build -f images/runtime/Dockerfile --build-arg VERSION="$(cat VERSION)" .
#
# Both binaries are cross-compiled on the build platform, so a multi-platform
# build needs no emulation.

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


FROM --platform=$BUILDPLATFORM golang:1.27-alpine AS entrypoint-builder
WORKDIR /build
COPY runtime/entrypoint/go.mod runtime/entrypoint/go.sum ./
RUN go mod download
COPY runtime/entrypoint/ ./
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /entrypoint ./cmd/ssebench-entrypoint


FROM scratch
COPY --from=daemon-builder /ssebench-daemon /ssebench/ssebench-daemon
COPY --from=entrypoint-builder /entrypoint /usr/local/bin/entrypoint
