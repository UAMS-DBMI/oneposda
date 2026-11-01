.PHONY: everything push push-multiplatform

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


push:
	make -C web push
	make -C posda push
	make -C lanterna push
	make -C kaleidoscope push
	make -C ream push
	make -C exodus push
	make -C nopperabo push

# Only web is cheap to build multi-platform (its builder stages run on the
# build host); everything else is native-only via `push`.
push-multiplatform:
	make -C web push-multiplatform
