# Build base images
base-images: _check-main-ahead
    echo "==> Invoking images/base-images/Makefile"
    make -C images/base-images all

# Build case images (all tasks by default, or specify tasks as comma-separated list)
# Options: --force to rebuild
case-build *args: _check-main-ahead
    #!/usr/bin/env bash
    set -euo pipefail
    force=""
    tasks=""
    for arg in {{args}}; do
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

# Clean all case images
case-clean:
    @echo "Removing all case images..."
    @docker images --format '{{ "{{.Repository}}:{{.Tag}}" }}' | grep -F "${SSEBENCH_REGISTRY:-ghcr.io/42-b3yond-6ug/ssebench}/case/" | xargs -r docker rmi || echo "No case images to remove"
