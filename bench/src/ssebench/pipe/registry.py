import os

# Prefix of every image SSEBench builds or pulls; override it to use another registry.
REGISTRY = os.environ.get("SSEBENCH_REGISTRY", "ghcr.io/42-b3yond-6ug/ssebench").rstrip("/")
