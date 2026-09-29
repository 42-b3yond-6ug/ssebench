#!/bin/bash
# SSEBench SDK Integration Test Runner
#
# Usage: sdk/tests/integration/run_test.sh [OPTIONS]
#
# Options:
#   --no-cache    Build Docker image without cache
#   --interactive Run container in interactive mode for WebUI testing
#                 (keeps container running with SDK daemon accessible)
#   --with-agent  Also run the mock agent (writes dialog entries for WebUI)
#   --build-only  Only build the image, don't run tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The daemon builds from the repository-level Cargo workspace.
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "SSEBench SDK Integration Test"
echo "=========================================="

# Parse arguments
BUILD_ARGS=""
INTERACTIVE=false
BUILD_ONLY=false
WITH_AGENT=false

for arg in "$@"; do
	case $arg in
	--no-cache)
		BUILD_ARGS="--no-cache"
		echo "Building without cache..."
		;;
	--interactive)
		INTERACTIVE=true
		echo "Interactive mode enabled..."
		;;
	--with-agent)
		WITH_AGENT=true
		echo "Mock agent enabled..."
		;;
	--build-only)
		BUILD_ONLY=true
		echo "Build only mode..."
		;;
	esac
done

# Build the integration test image
echo ""
echo "Step 1: Building Docker image..."
echo "------------------------------------------"
docker build $BUILD_ARGS -f sdk/tests/integration/Dockerfile -t ssebench-sdk-integration .

if [ "$BUILD_ONLY" = true ]; then
	echo ""
	echo "Build completed. Skipping test run."
	exit 0
fi

# Common labels for SSEBench WebUI compatibility
LABELS=(
	"--label" "ssebench.webui=true"
	"--label" "ssebench.task-id=integration-test-001"
	"--label" "ssebench.model=test-model"
	"--label" "ssebench.agent=test-agent"
)

if [ "$INTERACTIVE" = true ]; then
	# Interactive mode: Run container with SDK daemon for WebUI testing
	echo ""
	echo "Step 2: Starting container in interactive mode..."
	echo "------------------------------------------"
	echo ""
	echo "Container will run with SDK daemon accessible on port 4263"
	echo "Use 'docker ps' to find the container ID"
	echo "Use 'docker stop <container_id>' to stop when done"
	echo ""

	# Ensure ssebench_net network exists (create if not)
	if ! docker network inspect ssebench_net >/dev/null 2>&1; then
		echo "Creating ssebench_net network..."
		docker network create ssebench_net
	fi

	# Clean up any existing test container
	docker rm -f ssebench-sdk-test 2>/dev/null || true

	# Build the startup command based on options
	if [ "$WITH_AGENT" = true ]; then
		# Run both SDK daemon and mock agent
		STARTUP_CMD="ssebench-daemon & python3 /mock_agent.py --loop & sleep infinity"
	else
		# Run only SDK daemon
		STARTUP_CMD="ssebench-daemon & sleep infinity"
	fi

	# Run container in background with daemon
	CONTAINER_ID=$(docker run -d \
		"${LABELS[@]}" \
		--name ssebench-sdk-test \
		--network ssebench_net \
		ssebench-sdk-integration \
		sh -c "$STARTUP_CMD")

	echo "Container started: $CONTAINER_ID"
	echo ""

	# Wait for daemon to start
	sleep 2

	# Get container IP
	CONTAINER_IP=$(docker inspect "$CONTAINER_ID" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')

	echo "=========================================="
	echo "Interactive test container running!"
	echo "=========================================="
	echo ""
	echo "Container ID:   $CONTAINER_ID"
	echo "Container Name: ssebench-sdk-test"
	echo "Container IP:   $CONTAINER_IP"
	echo "SDK URL:        http://$CONTAINER_IP:4263"
	if [ "$WITH_AGENT" = true ]; then
		echo "Mock Agent:     Running (dialog entries at /agent/dialog)"
	fi
	echo ""
	echo "Test commands:"
	echo "  curl http://$CONTAINER_IP:4263/version"
	echo "  curl http://$CONTAINER_IP:4263/project"
	echo "  curl http://$CONTAINER_IP:4263/files"
	echo "  curl http://$CONTAINER_IP:4263/diff"
	if [ "$WITH_AGENT" = true ]; then
		echo "  curl http://$CONTAINER_IP:4263/agent/dialog"
		echo "  curl 'http://$CONTAINER_IP:4263/agent/dialog?since=5'"
	fi
	echo ""
	echo "WebUI backend endpoints:"
	echo "  GET /api/containers/$CONTAINER_ID/sdk/health"
	echo "  GET /api/containers/$CONTAINER_ID/project"
	echo "  GET /api/containers/$CONTAINER_ID/files"
	echo "  GET /api/containers/$CONTAINER_ID/diff"
	if [ "$WITH_AGENT" = true ]; then
		echo "  GET /api/containers/$CONTAINER_ID/agent/dialog"
	fi
	echo ""
	echo "To stop: docker stop ssebench-sdk-test && docker rm ssebench-sdk-test"
	echo ""

	exit 0
fi

# Normal mode: Run tests
echo ""
echo "Step 2: Running integration tests..."
echo "------------------------------------------"
docker run --rm "${LABELS[@]}" ssebench-sdk-integration python3 /test_sdk.py
EXIT_CODE=$?

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
	echo "Integration tests PASSED"
else
	echo "Integration tests FAILED"
fi
echo "=========================================="

exit $EXIT_CODE
