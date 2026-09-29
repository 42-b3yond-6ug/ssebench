from ssebench import settings
from ssebench.version import VERSION

# Prefix of every image SSEBench builds or pulls; override it to use another registry.
REGISTRY = settings.get("SSEBENCH_REGISTRY", "ghcr.io/42-b3yond-6ug/ssebench").rstrip("/")

# Tag of the tool layer, sidecar runtime and agent images this version builds.
TAG = VERSION
