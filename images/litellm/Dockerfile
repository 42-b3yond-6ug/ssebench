# Build from the repository root, so that models/ is in the context.
# The configuration is generated on the build platform, so a multi-platform
# build runs nothing under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/berriai/litellm:v1.105.1@sha256:b7b9e2c306343721802253d0dd9436b9634a2eb4e14da7c7cf06c5c7b7530802 AS config
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml

FROM ghcr.io/berriai/litellm:v1.105.1@sha256:b7b9e2c306343721802253d0dd9436b9634a2eb4e14da7c7cf06c5c7b7530802
ENV CONFIG_FILE_PATH=/litellm-config.yaml
COPY --from=config /litellm-config.yaml /litellm-config.yaml
