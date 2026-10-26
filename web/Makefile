IMAGE_NAME := posda_web

MIRABELLE_COMMIT := $(shell git --git-dir=mirabelle/.git rev-parse HEAD)

# There are some filenames with spaces further down
MAXDEPTH := 2

include ../common.mk

## Must override the standard rule from common.mk so we can include
## the build-arg for MIRABELLE_COMMIT
$(STAMP_DIR)/image.stamp: ../common.mk Dockerfile $(shell find . -maxdepth $(MAXDEPTH) -type f -not -name "image.stamp") | $(STAMP_DIR)
	docker buildx build --platform linux/amd64 --push . \
		-t $(REGISTRY)/${IMAGE_NAME}:${GIT_TAG} \
		-t $(REGISTRY)/${IMAGE_NAME}:$(POSDA_IMG_VERSION) \
		--build-arg MIRABELLE_COMMIT="${MIRABELLE_COMMIT}"
	touch $@
