# Build the base images and the task-independent runtime images
[group('images')]
images: base-images runtime-images

# Build the base images that case images start from
[group('images')]
base-images:
    make -C images/base-images all SSEBENCH_REGISTRY="{{registry}}"

# Build the sidecar runtime, LiteLLM proxy and catalog images
[group('images')]
runtime-images:
    docker buildx build --load -f images/sidecar-agent/Dockerfile --build-arg VERSION="{{version}}" \
        -t "{{registry}}/runtime:{{version}}" .
    uv run ssebench proxy build
    docker buildx build --load -f catalog/Dockerfile --build-arg VERSION="{{version}}" \
        -t "{{registry}}/catalog:{{version}}" .

# Build case images of all pilot tasks or the named ones (comma-separated); --force rebuilds
[group('images')]
case-build *args:
    #!/usr/bin/env bash
    set -euo pipefail
    force=""
    tasks=""
    for arg in "$@"; do
        case "$arg" in
            --force) force="--force" ;;
            *) tasks="$arg" ;;
        esac
    done
    if [ -n "$tasks" ]; then
        echo "Building case images for: $tasks"
        uv run ssebench build-case --tasks "$tasks" $force
    else
        echo "Building case images for all tasks in datasets/pilot/"
        uv run ssebench build-case $force
    fi

# Remove all case images
[group('images')]
case-clean:
    @echo "Removing all case images..."
    @docker images --format '{{ "{{.Repository}}:{{.Tag}}" }}' | grep -F "{{registry}}/case/" | xargs -r docker rmi || echo "No case images to remove"
