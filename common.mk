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

IMAGE_TAGS := \
	-t $(REGISTRY)/$(IMAGE_NAME):$(GIT_TAG) \
	-t $(REGISTRY)/$(IMAGE_NAME):$(POSDA_IMG_VERSION)


STAMP_DIR := .make
$(STAMP_DIR):
	mkdir -p $@

# The maximum depth find will search for source files.
# Set it in a child Makefile if you need to limit it
MAXDEPTH ?= 10

default: build

.PHONY: info build test push push-multiplatform
info:
	@echo "VERSION: $(VERSION)"
	@echo "REGISTRY: $(REGISTRY)"
	@echo "IMAGE_NAME: $(IMAGE_NAME)"
	@echo "BUILD_ARGS: $(BUILD_ARGS)"

build: $(STAMP_DIR)/image.stamp

test: build
	docker run -it $(REGISTRY)/$(IMAGE_NAME):$(POSDA_IMG_VERSION) sh

# Push exactly the image that `build` produced (native platform only).
push: build
	docker image push $(REGISTRY)/$(IMAGE_NAME):$(GIT_TAG)
	docker image push $(REGISTRY)/$(IMAGE_NAME):$(POSDA_IMG_VERSION)

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
