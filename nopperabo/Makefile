IMAGE_NAME := nopperabo

# The masker submodule's commit is baked into its wheel version
MASKER_COMMIT := $(shell git -C masker rev-parse --short HEAD)
MASKER_GIT_DIR := $(shell git -C masker rev-parse --absolute-git-dir)

BUILD_ARGS := --build-arg GIT_COMMIT=$(MASKER_COMMIT)

include ../common.mk

# Rebuild whenever the masker submodule's checked-out commit changes.
$(STAMP_DIR)/image.stamp: $(MASKER_GIT_DIR)/HEAD

# Build masker itself
masker/dist/masker-1.0.3-py3-none-any.whl:
	# docker run -it --rm --user $(shell id -u):$(shell id -g) -v ${PWD}/masker:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"
	docker run -it --rm -v ${PWD}/masker:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"

# Build nopperabo wheel
dist/nopperabo-0.1.0-py3-none-any.whl: masker/dist/masker-1.0.3-py3-none-any.whl
	docker run -t --rm -v ${PWD}:/workdir python:3 /bin/bash -c "cd /workdir; pip install build; python -m build"
