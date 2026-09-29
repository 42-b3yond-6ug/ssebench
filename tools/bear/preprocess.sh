#!/bin/bash

set -e # Exit on error

BENCHMARK_DIR=./datasets/pilot
PROJECT=$*

# Error Codes
ERR_PROJECT_NON_EXIST=1
ERR_SSE_NON_EXIST=2
ERR_DOCKER_BUILD=3
ERR_DOCKER_RUN=4
ERR_COPY_FAIL=5

# Cleanup function
cleanup() {
  if [ -n "$DOCKER_CONTAINER_NAME" ] && docker container inspect "$DOCKER_CONTAINER_NAME" >/dev/null 2>&1; then
    echo "Cleaning up container: $DOCKER_CONTAINER_NAME"
    docker rm -f "$DOCKER_CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  if [ -n "$DOCKER_IMAGE_NAME" ] && docker image inspect "$DOCKER_IMAGE_NAME" >/dev/null 2>&1; then
    echo "Cleaning up image: $DOCKER_IMAGE_NAME"
    docker rmi "$DOCKER_IMAGE_NAME" >/dev/null 2>&1 || true
  fi
}

# Set trap for cleanup on script exit
trap cleanup EXIT

# check if the project exists
if [ ! -d "$BENCHMARK_DIR"/"$PROJECT" ]; then
  echo "ERROR: $PROJECT does not exist"
  exit $ERR_PROJECT_NON_EXIST
fi

# check if the project contains /sse folder (required)
if [ ! -d "$BENCHMARK_DIR"/"$PROJECT"/sse ]; then
  echo "ERROR: $PROJECT/sse folder does not exist"
  exit $ERR_SSE_NON_EXIST
fi

# check if the project contains `compile_commands.json`
if [ -f "$BENCHMARK_DIR"/"$PROJECT"/sse/compile_commands.json ]; then
  echo "INFO: $PROJECT contains compile_commands.json, skipping."
  exit 0
fi

echo "INFO: Building compilation database for $PROJECT"

# Build the temporary docker container
DOCKER_IMAGE_NAME="ssebench-preprocess-bear-$PROJECT"
echo "INFO: Building Docker image: $DOCKER_IMAGE_NAME"
if ! docker build -t "$DOCKER_IMAGE_NAME" "$BENCHMARK_DIR"/"$PROJECT"; then
  echo "ERROR: Failed to build Docker image"
  exit $ERR_DOCKER_BUILD
fi

# Generate unique container name
DOCKER_CONTAINER_NAME="ssebench-preprocess-bear-$PROJECT-$$"

echo "INFO: Running compilation with bear in container: $DOCKER_CONTAINER_NAME"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Launch docker container and run compilation with bear
if ! docker run --name "$DOCKER_CONTAINER_NAME" \
    --entrypoint="" \
    -v "$SCRIPT_DIR/compile_with_bear.sh:/tmp/compile_with_bear.sh:ro" \
    "$DOCKER_IMAGE_NAME" \
    bash /tmp/compile_with_bear.sh; then
  echo "ERROR: Failed to run compilation in Docker container"
  exit $ERR_DOCKER_RUN
fi

echo "INFO: Copying compile_commands.json from container"
if ! docker cp "$DOCKER_CONTAINER_NAME:/tmp/compile_commands.json" "$BENCHMARK_DIR/$PROJECT/sse/"; then
  echo "ERROR: Failed to copy compile_commands.json from container"
  exit $ERR_COPY_FAIL
fi

echo "SUCCESS: Compilation database generated for $PROJECT"
