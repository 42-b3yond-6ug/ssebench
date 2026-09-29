# ============================================================
# Makefile for base-images
# ============================================================

SSEBENCH_REGISTRY ?= ghcr.io/42-b3yond-6ug/ssebench
DOCKER        ?= docker
CONTEXT       := .
BUILD_FLAGS   :=

IMAGE_PREFIX  := $(SSEBENCH_REGISTRY)/base-
ROOT          := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../..
# Images are published with the SSEBench version and with latest.
VERSION       := $(shell cat $(ROOT)/VERSION)
TAGS          := $(VERSION) latest
# Task Dockerfiles pin the base images of a release, such as
# base-generic-go:1.0.0. Local builds are also tagged with every version that a
# dataset manifest names, so that case images build on them instead of pulling
# the release. Those tags are never pushed: they name another release.
MANIFESTS     := $(wildcard $(ROOT)/datasets/*/manifest.json)
DATASET_TAGS  := $(if $(MANIFESTS),$(shell sed -n 's/.*"base": "base-[^":@]*:\([^"@]*\)".*/\1/p' $(MANIFESTS) | sort -u))
BUILD_TAGS    := $(sort $(TAGS) $(DATASET_TAGS))

BASE_IMAGES := generic-c generic-rust generic-go

.PHONY: all $(BASE_IMAGES) build push clean help

## Build all base images
all: $(BASE_IMAGES)

## Build a specific base image (e.g., `make generic-c`)
$(BASE_IMAGES):
	@echo "==> Building $@"
	$(DOCKER) build $(BUILD_FLAGS) \
		-f $(CONTEXT)/$@/Dockerfile \
		$(foreach tag,$(BUILD_TAGS),-t $(IMAGE_PREFIX)$@:$(tag)) \
		$(CONTEXT)
	@echo "==> Built $(IMAGE_PREFIX)$@ ($(BUILD_TAGS))"

## Push all built images
push:
	@for img in $(BASE_IMAGES); do \
		for tag in $(TAGS); do \
			echo "==> Pushing $(IMAGE_PREFIX)$$img:$$tag"; \
			$(DOCKER) push $(IMAGE_PREFIX)$$img:$$tag || exit 1; \
		done; \
	done

## Remove all local base images
clean:
	@for img in $(BASE_IMAGES); do \
		for tag in $(BUILD_TAGS); do \
			echo "==> Removing $(IMAGE_PREFIX)$$img:$$tag"; \
			$(DOCKER) rmi -f $(IMAGE_PREFIX)$$img:$$tag || true; \
		done; \
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
	@echo "Tags:               $(BUILD_TAGS) (pushed: $(TAGS))"
	@echo "Source context:     $(CONTEXT)/"
	@echo ""

