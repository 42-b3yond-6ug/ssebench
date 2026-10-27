# Build from the repository root, so that models/ is in the context.
# The configuration is generated on the build platform, so a multi-platform
# build runs nothing under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/berriai/litellm:v1.106.4@sha256:c169fb3adc514fcf210377c203f3de406d54f10bfdacf13948a4a839db9af7de AS config
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml

FROM ghcr.io/berriai/litellm:v1.106.4@sha256:c169fb3adc514fcf210377c203f3de406d54f10bfdacf13948a4a839db9af7de
ENV CONFIG_FILE_PATH=/litellm-config.yaml
COPY --from=config /litellm-config.yaml /litellm-config.yaml
