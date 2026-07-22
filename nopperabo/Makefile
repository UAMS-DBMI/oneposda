IMAGE_NAME := nopperabo

default_override: build-special
include ../common.mk

.PHONY: build-special push

SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MASKER := $(shell git rev-parse HEAD)

default: build

# Build masker itself
masker/dist/masker-1.0.3-py3-none-any.whl:
	# docker run -it --rm --user $(shell id -u):$(shell id -g) -v ${PWD}/masker:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"
	docker run -it --rm -v ${PWD}/masker:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"

# Build nopperabo wheel
dist/nopperabo-0.1.0-py3-none-any.whl: masker/dist/masker-1.0.3-py3-none-any.whl
	docker run -t --rm -v ${PWD}:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"

# Build actual docker image
# carefully get the git commit from the masker submodule
.ONESHELL:
build-special: Dockerfile # masker/dist/masker-1.0.3-py3-none-any.whl dist/nopperabo-0.1.0-py3-none-any.whl
	docker build --build-arg GIT_COMMIT=$(shell git --git-dir=masker/.git rev-parse --short HEAD) \
		-t $(REGISTRY)/$(IMAGE_NAME):${POSDA_IMG_VERSION} \
		-t $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG} \
		.

push: 
	docker image push $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG}
	docker image push $(REGISTRY)/${IMAGE_NAME}:${POSDA_IMG_VERSION} 
