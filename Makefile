.PHONY: everything push push-manifest push-multiplatform

# Subdirs that build an image via common.mk
IMAGE_DIRS := web posda lanterna kaleidoscope ream exodus nopperabo

default: everything

everything:
	# git submodule init
	# git submodule update
	# make -C docs
	# make -C ohif
	make -C web
	make -C posda
	make -C lanterna
	make -C kaleidoscope
	make -C ream
	make -C exodus
	make -C nopperabo


# Pushes native-arch images (VERSION-amd64 etc). Plain VERSION tags are
# only pushed from the primary arch; see common.mk.
push:
	$(foreach d,$(IMAGE_DIRS),make -C $(d) push &&) true

# After `make push` has run on every arch in MANIFEST_ARCHES at this commit,
# merge them into multi-platform VERSION tags.
push-manifest:
	$(foreach d,$(IMAGE_DIRS),make -C $(d) push-manifest &&) true

# Only web is cheap to build multi-platform (its builder stages run on the
# build host); everything else is native-only via `push`.
push-multiplatform:
	make -C web push-multiplatform
