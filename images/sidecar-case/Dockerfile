FROM rust:1.83.0-alpine AS daemon-builder
RUN apk add --no-cache musl-dev
WORKDIR /build
COPY sdk/daemon/Cargo.toml sdk/daemon/Cargo.lock ./
COPY sdk/daemon/src/ ./src/
RUN cargo build --release --locked --bin ssebench-daemon


FROM case-image AS case-image-builder

FROM case-image
ARG SOURCE_DIR

# Stash original source as a root-only snapshot, re-populate owned by model (uid 1000)
RUN mv "${SOURCE_DIR}" /ssebench-repo && chmod 700 /ssebench-repo
COPY --from=case-image-builder --chown=1000:1000 ${SOURCE_DIR}/ ${SOURCE_DIR}/

# Create model user, init clean git repo
COPY --chmod=755 images/common/setup-source.sh /tmp/setup-source.sh
RUN /tmp/setup-source.sh "${SOURCE_DIR}" && rm /tmp/setup-source.sh

COPY --from=daemon-builder /build/target/release/ssebench-daemon /ssebench/ssebench-daemon

COPY --chmod=700 images/sidecar-case/entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT [ "/usr/local/bin/entrypoint.sh" ]
