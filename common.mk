VERSION := 1.1.19
REGISTRY := registry.dbmi.cloud
GIT_TAG := $(shell git rev-parse --short HEAD)

POSDA_IMG_VERSION := $(VERSION)


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

push: build
	docker image push $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG}
	docker image push $(REGISTRY)/${IMAGE_NAME}:${POSDA_IMG_VERSION} 

test: build
	docker run -it $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION) sh

$(STAMP_DIR)/image.stamp: ../common.mk Dockerfile $(shell find . -maxdepth $(MAXDEPTH) -type f -not -name "image.stamp") | $(STAMP_DIR)
	docker build .  \
		-t $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG} \
		-t $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION) 
	touch $@
