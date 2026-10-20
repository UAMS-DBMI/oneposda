VERSION := 1.1.20-multiplat-test
REGISTRY := registry.dbmi.cloud
GIT_TAG := $(shell git rev-parse --short HEAD)

POSDA_IMG_VERSION := $(VERSION)

# Platforms built by `push`. `build`/`test` only build the host's native
# platform so the image can be loaded and run locally.
PLATFORMS ?= linux/amd64,linux/arm64


STAMP_DIR := .make
$(STAMP_DIR):
	mkdir -p $@

# The maximum depth find will search for source files.
# Set it in a child Makefile if you need to limit it
MAXDEPTH ?= 10

default: build

.PHONY: info push build
info:
	@echo "VERSION: $(VERSION)"
	@echo "REGISTRY: $(REGISTRY)"

build: $(STAMP_DIR)/image.stamp

# Multi-platform build straight to the registry. Does not depend on `build`:
# the native layers are already in the buildx cache, so only the emulated
# platform(s) actually get built here. Override with e.g. PLATFORMS=linux/amd64.
push:
	docker buildx build --platform $(PLATFORMS) --push . \
		-t $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG} \
		-t $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION)

test: build
	docker run -it $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION) sh

$(STAMP_DIR)/image.stamp: ../common.mk Dockerfile $(shell find . -maxdepth $(MAXDEPTH) -type f -not -name "image.stamp") | $(STAMP_DIR)
	docker buildx build --load . \
		-t $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG} \
		-t $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION)
	touch $@
