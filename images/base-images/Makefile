# ============================================================
# Makefile for base-images
# ============================================================

SSEBENCH_REGISTRY ?= ghcr.io/42-b3yond-6ug/ssebench
DOCKER        ?= docker
CONTEXT       := .
BUILD_FLAGS   :=

IMAGE_PREFIX  := $(SSEBENCH_REGISTRY)/base-

BASE_IMAGES := generic-c generic-rust generic-go

.PHONY: all $(BASE_IMAGES) build push clean help

## Build all base images
all: $(BASE_IMAGES)

## Build a specific base image (e.g., `make generic-c`)
$(BASE_IMAGES):
	@echo "==> Building $@"
	$(DOCKER) build $(BUILD_FLAGS) \
		-f $(CONTEXT)/$@/Dockerfile \
		-t $(IMAGE_PREFIX)$@:latest \
		$(CONTEXT)
	@echo "==> Built $(IMAGE_PREFIX)$@:latest"

## Push all built images
push:
	@for img in $(BASE_IMAGES); do \
		echo "==> Pushing $(IMAGE_PREFIX)$$img:latest"; \
		$(DOCKER) push $(IMAGE_PREFIX)$$img:latest; \
	done

## Remove all local base images
clean:
	@for img in $(BASE_IMAGES); do \
		echo "==> Removing $(IMAGE_PREFIX)$$img:latest"; \
		$(DOCKER) rmi -f $(IMAGE_PREFIX)$$img:latest || true; \
	done

## Display available targets
help:
	@echo ""
	@echo "Available targets:"
	@echo "  make all          - Build all base images"
	@echo "  make <image>      - Build one base image (e.g., generic-c)"
	@echo "  make push         - Push all images to registry"
	@echo "  make clean        - Remove all local images"
	@echo ""
	@echo "Registry prefix:    $(IMAGE_PREFIX)"
	@echo "Source context:     $(CONTEXT)/"
	@echo ""

