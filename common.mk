VERSION := 1.1.20-multiplat-test
REGISTRY := registry.dbmi.cloud
GIT_TAG := $(shell git rev-parse --short HEAD)

POSDA_IMG_VERSION := $(VERSION)

# Platforms built by `push-multiplatform`. `build`, `test` and `push` only
# use the host's native platform. Non-native platforms run under QEMU and
# are very slow, so only images whose Dockerfiles are set up for it (builder
# stages pinned to $BUILDPLATFORM) should bother.
PLATFORMS ?= linux/amd64,linux/arm64

# Extra flags for every `docker buildx build`. Child Makefiles that need
# --build-arg (commit SHAs etc.) set this instead of overriding the rules.
BUILD_ARGS ?=

# Native arch of the docker daemon, in docker's naming (amd64, arm64).
ARCH := $(shell docker version --format '{{.Server.Arch}}' 2>/dev/null)

# Every `push` publishes arch-suffixed tags (VERSION-amd64 etc). Only the
# primary arch also publishes the plain tags, so a `make push` from an arm64
# laptop can never overwrite what the servers pull. `push-manifest` later
# merges the per-arch tags for MANIFEST_ARCHES into multi-platform plain tags.
PRIMARY_ARCH ?= amd64
MANIFEST_ARCHES ?= amd64 arm64

IMAGE := $(REGISTRY)/$(IMAGE_NAME)
IMAGE_TAGS := \
	-t $(IMAGE):$(GIT_TAG) \
	-t $(IMAGE):$(POSDA_IMG_VERSION) \
	-t $(IMAGE):$(GIT_TAG)-$(ARCH) \
	-t $(IMAGE):$(POSDA_IMG_VERSION)-$(ARCH)


STAMP_DIR := .make
$(STAMP_DIR):
	mkdir -p $@

# The maximum depth find will search for source files.
# Set it in a child Makefile if you need to limit it
MAXDEPTH ?= 10

default: build

.PHONY: info build test push push-manifest push-multiplatform
info:
	@echo "VERSION: $(VERSION)"
	@echo "REGISTRY: $(REGISTRY)"
	@echo "IMAGE_NAME: $(IMAGE_NAME)"
	@echo "BUILD_ARGS: $(BUILD_ARGS)"
	@echo "ARCH: $(ARCH) (primary: $(PRIMARY_ARCH))"

build: $(STAMP_DIR)/image.stamp

test: build
	docker run -it $(IMAGE):$(POSDA_IMG_VERSION) sh

# Push exactly the image that `build` produced (native platform only).
push: build
	@test -n "$(ARCH)" || { echo "Could not detect docker daemon arch"; exit 1; }
	docker image push $(IMAGE):$(GIT_TAG)-$(ARCH)
	docker image push $(IMAGE):$(POSDA_IMG_VERSION)-$(ARCH)
ifeq ($(ARCH),$(PRIMARY_ARCH))
	docker image push $(IMAGE):$(GIT_TAG)
	docker image push $(IMAGE):$(POSDA_IMG_VERSION)
endif

# Combine the already-pushed per-arch images for this commit into
# multi-platform plain tags. Runs entirely in the registry; fails if any arch
# in MANIFEST_ARCHES has not been pushed for this GIT_TAG.
push-manifest:
	docker buildx imagetools create \
		-t $(IMAGE):$(GIT_TAG) \
		-t $(IMAGE):$(POSDA_IMG_VERSION) \
		$(foreach a,$(MANIFEST_ARCHES),$(IMAGE):$(GIT_TAG)-$(a))

# Opt-in multi-platform build straight to the registry. Does not depend on
# `build`: the native layers are already in the buildx cache, so only the
# emulated platform(s) actually get built here.
push-multiplatform:
	docker buildx build --platform $(PLATFORMS) --push . \
		$(BUILD_ARGS) $(IMAGE_TAGS)

# Child Makefiles can add prerequisites with another
# `$(STAMP_DIR)/image.stamp: extra-file` line after the include.
$(STAMP_DIR)/image.stamp: ../common.mk Dockerfile $(shell find . -maxdepth $(MAXDEPTH) -type f -not -name "image.stamp") | $(STAMP_DIR)
	docker buildx build --load . \
		$(BUILD_ARGS) $(IMAGE_TAGS)
	touch $@
