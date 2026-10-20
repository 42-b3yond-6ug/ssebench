# Build from the repository root, so that models/ is in the context.
# The configuration is generated on the build platform, so a multi-platform
# build runs nothing under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/berriai/litellm:v1.106.0@sha256:2e4c0371f3a8c28e4da131d77abaa8341cd3b0c2fcc4d34d7c5900431af7b9d0 AS config
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml

FROM ghcr.io/berriai/litellm:v1.106.0@sha256:2e4c0371f3a8c28e4da131d77abaa8341cd3b0c2fcc4d34d7c5900431af7b9d0
ENV CONFIG_FILE_PATH=/litellm-config.yaml
COPY --from=config /litellm-config.yaml /litellm-config.yaml
