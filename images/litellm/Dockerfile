# Build from the repository root, so that models/ is in the context.
# The configuration is generated on the build platform, so a multi-platform
# build runs nothing under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/berriai/litellm:v1.103.1@sha256:df15400b5b80925c45d3fd53f8f7a6c0eaa8a25a86833e1b358002e129018943 AS config
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml

FROM ghcr.io/berriai/litellm:v1.103.1@sha256:df15400b5b80925c45d3fd53f8f7a6c0eaa8a25a86833e1b358002e129018943
ENV CONFIG_FILE_PATH=/litellm-config.yaml
COPY --from=config /litellm-config.yaml /litellm-config.yaml
