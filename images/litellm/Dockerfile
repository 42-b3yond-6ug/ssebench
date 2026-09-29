FROM ghcr.io/berriai/litellm:main-latest

# Set LiteLLM configuration path
ENV CONFIG_FILE_PATH=/litellm-config.yaml

# Generate LiteLLM configuration
COPY models /models
COPY images/litellm/config_gen.py /config_gen.py
RUN python3 /config_gen.py > /litellm-config.yaml
