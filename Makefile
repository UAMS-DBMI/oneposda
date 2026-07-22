.PHONY: everything push

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
