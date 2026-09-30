# Cross-compiled on the build platform, as in images/runtime, so building for
# another architecture needs no emulation here.
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


# The daemon, laid out like the runtime image (images/runtime). Passing
#   --build-context runtime=docker-image://<registry>/runtime:<version>
# replaces this stage, and skips the build above.
FROM scratch AS runtime
COPY --from=daemon-builder /ssebench-daemon /ssebench/ssebench-daemon


FROM case-image AS case-image-builder

FROM case-image
ARG SOURCE_DIR

# Stash original source as a root-only snapshot, re-populate owned by model (uid 1000).
# /ssebench holds the reference patch and hidden tests, so it is root-only too.
RUN mv "${SOURCE_DIR}" /ssebench-repo && chmod 700 /ssebench-repo && chmod 700 /ssebench
COPY --from=case-image-builder --chown=1000:1000 ${SOURCE_DIR}/ ${SOURCE_DIR}/

# Create model user, init clean git repo
COPY --chmod=755 images/common/setup-source.sh /tmp/setup-source.sh
RUN /tmp/setup-source.sh "${SOURCE_DIR}" && rm /tmp/setup-source.sh

COPY --from=runtime /ssebench/ssebench-daemon /ssebench/ssebench-daemon

COPY --chmod=700 images/sidecar-case/entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT [ "/usr/local/bin/entrypoint.sh" ]
