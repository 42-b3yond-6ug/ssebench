# Build from the repository root, so that models/ is in the context.
# The configuration is generated on the build platform, so a multi-platform
# build runs nothing under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/berriai/litellm:v1.106.6@sha256:37e2dafb088a7723beb998590682957386dfc83ffea1848486f8e0e5cfac0b06 AS config
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml

FROM ghcr.io/berriai/litellm:v1.106.6@sha256:37e2dafb088a7723beb998590682957386dfc83ffea1848486f8e0e5cfac0b06
ENV CONFIG_FILE_PATH=/litellm-config.yaml
COPY --from=config /litellm-config.yaml /litellm-config.yaml
