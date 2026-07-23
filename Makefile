# F9070W toolchain. `make` with no arguments prints the target list.
#
# Nothing here writes to a device. Flashing is forbidden until the recovery path
# is verified on hardware - see docs/hardware.md and rule 8 in AGENTS.md.

PY    := ./.venv/bin/python
THEME ?= vw

# A theme is a name under themes/, or a path to a directory. Empty when neither.
THEME_DIR = $(shell if [ -d "themes/$(THEME)" ]; then echo "themes/$(THEME)"; \
                    elif [ -d "$(THEME)" ]; then echo "$(THEME)"; fi)

NEED_VENV = @test -x $(PY) || { \
	echo 'missing $(PY)'; \
	echo 'create it with:'; \
	echo '  python3 -m venv .venv && ./.venv/bin/pip install pillow pytest'; \
	exit 1; }

NEED_THEME = @test -n "$(THEME_DIR)" || { \
	echo 'no such theme: "$(THEME)" is neither themes/$(THEME) nor a directory'; \
	echo 'themes/ holds:'; \
	ls themes 2>/dev/null | sed 's/^/  /' || echo '  (nothing)'; \
	echo 'THEME may also be a path: make $@ THEME=/tmp/my-theme'; \
	exit 1; }

.DEFAULT_GOAL := help

.PHONY: help unpack png test test-stock build img

help:
	@echo 'F9070W - reverse-engineered toolchain for the F9070W head unit.'
	@echo 'Read README.md first; AGENTS.md before changing any code.'
	@echo
	@echo 'make unpack SRC=<file>   unpack a firmware .rar or .img into stock/'
	@echo '                         e.g. make unpack SRC=~/Downloads/F9070W.rar'
	@echo '                         SRC is required; it rewrites stock/'
	@echo 'make png                 re-export every stock sprite to stock/png/'
	@echo 'make test                fast suite, no stock/ tree needed (~1 s)'
	@echo 'make test-stock          full suite against stock/ (~3 min)'
	@echo 'make build THEME=$(THEME)      theme PNGs -> out/apps/Data/*.data'
	@echo 'make img   THEME=$(THEME)      the above, plus out/LTTF133.img'
	@echo
	@echo 'THEME defaults to "$(THEME)" and is a name under themes/ or a path.'
	@echo 'An empty theme is rejected by build (there is nothing to write) but'
	@echo 'is valid for img, where it must reproduce stock/LTTF133.img exactly.'
	@echo
	@echo 'There is deliberately no flash target. See docs/hardware.md.'

unpack:
	$(NEED_VENV)
	@test -n "$(SRC)" || { \
		echo 'unpack needs a source: make unpack SRC=<path to .rar or .img>'; \
		echo '  make unpack SRC=~/Downloads/F9070W.rar'; \
		echo '  make unpack SRC=stock/LTTF133.img'; \
		exit 1; }
	@src=$$(eval echo "$(SRC)"); \
	 test -e "$$src" || { echo "no such file: $$src"; exit 1; }; \
	 echo "$(PY) tools/unpack.py $$src"; \
	 $(PY) tools/unpack.py "$$src"

png:
	$(NEED_VENV)
	$(PY) tools/unpack.py --png

test:
	$(NEED_VENV)
	$(PY) -m pytest -q -m "not stock"

test-stock:
	$(NEED_VENV)
	$(PY) tools/verify.py -q

build:
	$(NEED_VENV)
	$(NEED_THEME)
	$(PY) tools/build.py "$(THEME_DIR)"

img:
	$(NEED_VENV)
	$(NEED_THEME)
	$(PY) tools/build.py "$(THEME_DIR)" --img
