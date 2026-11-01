IMAGE_NAME := posda_web

MIRABELLE_COMMIT := $(shell git -C mirabelle rev-parse HEAD)
MIRABELLE_GIT_DIR := $(shell git -C mirabelle rev-parse --absolute-git-dir)

BUILD_ARGS := --build-arg MIRABELLE_COMMIT=$(MIRABELLE_COMMIT)

# There are some filenames with spaces further down
MAXDEPTH := 2

include ../common.mk

# MAXDEPTH keeps find from seeing deep changes inside the mirabelle
# submodule, so also rebuild whenever the submodule's checked-out commit
# changes.
$(STAMP_DIR)/image.stamp: $(MIRABELLE_GIT_DIR)/HEAD
