PY ?= .venv/bin/python
CMAKE ?= cmake
PANDOC ?= pandoc
HEXDUMP ?= hexdump -C
NPROC ?= $(shell nproc)
BENCH_REPEAT ?= 100

ROSPCC_PARSER := rospocc/parser.py
ROSPOAS_COMPILE := rospoas/compile.py
FONT_GEN := tools/generate_fb_map_data.py
FONT_SRC := tools/font8x8_basic_data.h

DIR_ROSPOS_BUILD := rospos/build
DIR_ROSPOVM_BUILD := rospovm/build
DIR_ROSPOVM_WASM_BUILD := rospovm/build-wasm
DIR_DOCS_BUILD := build/

ROS_SOURCE := rospos/main.rosc
ROS_ASM := $(DIR_ROSPOS_BUILD)/rospos.ros

ROSP_FULL := $(DIR_ROSPOS_BUILD)/rospos.rosp
ROSP_DEBC := $(DIR_ROSPOS_BUILD)/rospos_debc.rosp
ROSP_BINC := $(DIR_ROSPOS_BUILD)/rospos_binc.rosp
ROSP_COMBINED := $(DIR_ROSPOS_BUILD)/rospos_c.rosp
ROSP_VARIANTS := $(ROSP_FULL) $(ROSP_DEBC) $(ROSP_BINC) $(ROSP_COMBINED)

DOCS := Design.md Ideas.md Log.md
HTMLDOCS := $(addprefix $(DIR_DOCS_BUILD),$(DOCS:.md=.html))
PDFDOCS := $(addprefix $(DIR_DOCS_BUILD),$(DOCS:.md=.pdf))

ROSPOAS_COMMON_ARGS := --optimize --bin-version 2 --rospocc-mapping --segment-debug
ROSPO_VERBOSE_ARG := $(if $(filter 3 -vvv,$(VERBOSE)),-vvv,$(if $(filter 2 -vv,$(VERBOSE)),-vv,$(if $(VERBOSE),-v,)))

ROSPOAS_DEP := $(sort $(shell find rospoas -maxdepth 1 -type f) rospolog.py requirements.txt)
ROSPCC_DEP := $(sort $(shell find rospocc -maxdepth 1 -type f) rospolog.py requirements.txt)
ROSPOS_DEP := $(sort $(shell find rospos -type f -not -path "rospos/build/*"))
ROSPOVM_SRC := $(sort $(shell find rospovm -type f -not -path "rospovm/build/*"))

.DEFAULT_GOAL := build

.PHONY: all help venv bm parse compile dump build clean doc format frontend \
		frontend_cmake frontend_wasm frontend_wasm_light frontend_wasm_dark \
		frontend_wasm_both frontend_wasm_minimal frontend_wasm_full run     \ 
		vm_headless run_headless test report benchmark benchmark_plot       \
		everything frontend_minimal run_minimal	min_run vm_fuzz_harness 

all: build

venv:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

help:
	@echo "Common targets:"
	@echo "  venv             Create the root .venv and install Python dependencies"
	@echo "  bm               Generate font bitmap binary"
	@echo "  parse            Compile .rosc to .ros"
	@echo "  compile          Assemble all .rosp output variants"
	@echo "  frontend         Build Qt VM frontend"
	@echo "  frontend_wasm    Set up WASM dependencies and build frontend"
	@echo "  frontend_minimal Build minimal VM frontend"
	@echo "  vm_headless      Build headless VM"
	@echo "  run              Run with Qt frontend"
	@echo "  run_minimal      Run with minimal frontend"
	@echo "  run_headless     Run with headless VM"
	@echo "  min_run 		  Run with minimal frontend without full rebuild"
	@echo "  doc              Build HTML and PDF docs"
	@echo "  test             Run test suite"
	@echo "  benchmark        Run benchmark suite"
	@echo "  benchmark_plot   Plot benchmark metric trends over time"
	@echo "  report           Generate project report"
	@echo "  build            Full project build"
	@echo "  everything       Build + docs + benchmark + report"

$(DIR_ROSPOS_BUILD) $(DIR_ROSPOVM_BUILD) $(DIR_DOCS_BUILD):
	mkdir -p $@

rospos/font_bitmap.bin: $(FONT_GEN) $(FONT_SRC)
	mkdir -p $(dir $@)
	$(PY) $(FONT_GEN) --output $@ --input $(FONT_SRC) 1>&2

$(ROS_ASM): $(ROS_SOURCE) $(ROSPCC_DEP) $(ROSPOS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) $(ROSPCC_PARSER) $(ROSPO_VERBOSE_ARG) --input $< --output $@

define make_rosp_variant
$1: $(ROS_ASM) $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) $(ROSPOAS_COMPILE) $(ROSPOAS_COMMON_ARGS) $(ROSPO_VERBOSE_ARG) $2 --input $$< --output $$@
endef

$(eval $(call make_rosp_variant,$(ROSP_FULL),--debug-all))
$(eval $(call make_rosp_variant,$(ROSP_DEBC),--compress-debug))
$(eval $(call make_rosp_variant,$(ROSP_BINC),--compress-bin))
$(eval $(call make_rosp_variant,$(ROSP_COMBINED),--compress-bin --compress-debug))

$(DIR_ROSPOVM_BUILD)/Makefile: rospovm/CMakeLists.txt | $(DIR_ROSPOVM_BUILD)
	$(CMAKE) -S rospovm -B $(DIR_ROSPOVM_BUILD)

define make_vm_target
$(DIR_ROSPOVM_BUILD)/.$1.stamp: $(DIR_ROSPOVM_BUILD)/Makefile $(ROSPOVM_SRC)
	$(CMAKE) --build $(DIR_ROSPOVM_BUILD) --target $1 -j $(NPROC)
	@touch $$@

$(DIR_ROSPOVM_BUILD)/$1: $(DIR_ROSPOVM_BUILD)/.$1.stamp
endef

$(eval $(call make_vm_target,rospovm_qt))
$(eval $(call make_vm_target,rospovm_headless))
$(eval $(call make_vm_target,rospovm_minimal))

$(DIR_DOCS_BUILD)%.html: doc/%.md | $(DIR_DOCS_BUILD)
	$(PANDOC) $< --filter pandoc-include -s -o $@
	# Widen generated Pandoc layout for improved readability on wide displays.
	sed -i 's/max-width: 36em;/max-width: 64em;/g' $@

$(DIR_DOCS_BUILD)%.pdf: doc/%.md | $(DIR_DOCS_BUILD)
	$(PANDOC) $< --filter pandoc-include -V links-as-notes=true -o $@

rosbdump.txt: $(ROSP_FULL)
	$(PY) tools/rosb_tool.py inspect rospos.blockdev --show-data > rospbdump.txt
rbdump: rosbdump.txt
doc: $(HTMLDOCS) $(PDFDOCS)

bm: rospos/font_bitmap.bin
parse: $(ROS_ASM)
compile: $(ROSP_VARIANTS)
frontend_cmake: $(DIR_ROSPOVM_BUILD)/Makefile
frontend: $(DIR_ROSPOVM_BUILD)/rospovm_qt
frontend_minimal: $(DIR_ROSPOVM_BUILD)/rospovm_minimal
vm_headless: $(DIR_ROSPOVM_BUILD)/rospovm_headless


QT_VERSION ?= 6.12.0
QT_ROOT ?= $(HOME)/Qt/$(QT_VERSION)
QT_WASM ?= $(QT_ROOT)/wasm_singlethread
QT_NATIVE ?= $(QT_ROOT)/gcc_64
QT_WASM_CMAKE ?= $(QT_WASM)/bin/qt-cmake

EMSDK_VERSION ?= 5.0.5
EMSDK_DIR ?= $(abspath .deps/emsdk)
ECM_DIR ?= /usr/share/ECM/cmake

KF_VERSION ?= 6.30.0
KF_SOURCE := $(abspath .deps/src/syntax-highlighting-$(KF_VERSION))
KF_BUILD := $(abspath .deps/build/kf-$(KF_VERSION)-qt-$(QT_VERSION)-singlethread-em-$(EMSDK_VERSION))
KF_PREFIX := $(KF_BUILD)/install
KF_ECM := $(KF_BUILD)/ecm
KF_WASM_PATCH := $(abspath tools/patches/syntax-highlighting-wasm.patch)
KF_MINIMAL_SYNTAX_PATCH := $(abspath tools/patches/syntax-highlighting-minimal.patch)
# Set OFF to restore the complete upstream syntax collection.
KF_MINIMAL_SYNTAX ?= ON

HIGHLIGHTING_DIR := $(abspath rospovm/highlighting)
WASM_CMAKE_ARGS ?=

# Recipe lines run in separate shells; load the SDK for each build command.
# Host Qt tools must load this kit's libraries before any system Qt libraries.
WASM_RUN = EMSDK_QUIET=1 bash -c 'source "$(EMSDK_DIR)/emsdk_env.sh" && export LD_LIBRARY_PATH="$(QT_NATIVE)/lib$${LD_LIBRARY_PATH:+:$$LD_LIBRARY_PATH}" && exec "$$@"' --

.PHONY: wasm_sdk wasm_dependencies

$(EMSDK_DIR)/emsdk:
	mkdir -p "$(dir $(EMSDK_DIR))"
	git clone --depth 1 \
		https://github.com/emscripten-core/emsdk.git "$(EMSDK_DIR)"

wasm_sdk: $(EMSDK_DIR)/emsdk
	"$(EMSDK_DIR)/emsdk" install "$(EMSDK_VERSION)"
	"$(EMSDK_DIR)/emsdk" activate "$(EMSDK_VERSION)"

$(KF_SOURCE)/CMakeLists.txt:
	mkdir -p "$(dir $(KF_SOURCE))"
	git clone --depth 1 --branch "v$(KF_VERSION)" \
		https://invent.kde.org/frameworks/syntax-highlighting.git \
		"$(KF_SOURCE)"

# Use target-compatible resource compression and omit the native-only CLI.
$(KF_SOURCE)/.wasm-ready: $(KF_SOURCE)/CMakeLists.txt $(KF_WASM_PATCH)
	git -C "$(KF_SOURCE)" apply "$(KF_WASM_PATCH)"
	touch "$@"

# Keep this separate so existing checkouts can retain the applied WASM patch.
$(KF_SOURCE)/.minimal-syntax-ready: $(KF_SOURCE)/.wasm-ready $(KF_MINIMAL_SYNTAX_PATCH)
	git -C "$(KF_SOURCE)" apply "$(KF_MINIMAL_SYNTAX_PATCH)"
	touch "$@"

# ECM 6.30 adds an ELF linker flag on all Unix platforms, including WASM.
# Patch a private copy so the native indexer retains its normal Linux flags.
$(KF_ECM)/.wasm-ready: $(ECM_DIR)/ECMConfig.cmake $(ECM_DIR)/../kde-modules/KDECompilerSettings.cmake Makefile
	mkdir -p "$(KF_ECM)/share/ECM"
	cp -R "$(ECM_DIR)/../." "$(KF_ECM)/share/ECM/"
	sed -i 's/if (UNIX AND NOT APPLE AND NOT CYGWIN)/if (UNIX AND NOT APPLE AND NOT CYGWIN AND NOT EMSCRIPTEN)/' \
		"$(KF_ECM)/share/ECM/kde-modules/KDECompilerSettings.cmake"
	touch "$@"

wasm_dependencies: wasm_sdk $(KF_SOURCE)/.minimal-syntax-ready $(KF_ECM)/.wasm-ready
	$(WASM_RUN) "$(QT_WASM_CMAKE)" \
		-S "$(KF_SOURCE)" -B "$(KF_BUILD)" \
		-DQT_HOST_PATH="$(QT_NATIVE)" \
		-DECM_DIR="$(KF_ECM)/share/ECM/cmake" \
		-DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_INSTALL_PREFIX="$(KF_PREFIX)" \
		-DKDE_INSTALL_LIBDIR=lib \
		-DBUILD_SHARED_LIBS=OFF \
		-DBUILD_TESTING=OFF \
		-DBUILD_codeeditor=OFF \
		-DBUILD_codepdfprinter=OFF \
		-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Qml=ON \
		-DCMAKE_DISABLE_FIND_PACKAGE_Qt6Quick=ON \
		-DCMAKE_AUTORCC_OPTIONS=--compress-algo=zlib \
		-DKSYNTAXHIGHLIGHTING_USE_GUI=ON \
		-DROSPOS_MINIMAL_SYNTAX=$(KF_MINIMAL_SYNTAX) \
		-DQRC_SYNTAX=ON
	$(WASM_RUN) $(CMAKE) --build "$(KF_BUILD)" --parallel $(NPROC)
	$(WASM_RUN) $(CMAKE) --install "$(KF_BUILD)"

frontend_wasm: frontend_wasm_minimal frontend_wasm_full

frontend_wasm_full: wasm_dependencies $(ROSP_FULL)
	$(WASM_RUN) "$(QT_WASM_CMAKE)" \
		-S rospovm -B "$(DIR_ROSPOVM_WASM_BUILD)" \
		-DQT_HOST_PATH="$(QT_NATIVE)" \
		-DKF6SyntaxHighlighting_DIR="$(KF_PREFIX)/lib/cmake/KF6SyntaxHighlighting" \
		"-DCMAKE_EXE_LINKER_FLAGS=--preload-file $(HIGHLIGHTING_DIR)@$(HIGHLIGHTING_DIR)" \
		$(WASM_CMAKE_ARGS)
	$(WASM_RUN) $(CMAKE) --build "$(DIR_ROSPOVM_WASM_BUILD)" \
		--target rospovm_html --parallel $(NPROC)

frontend_wasm_minimal: wasm_sdk $(ROSP_FULL)
	$(WASM_RUN) "$(QT_WASM_CMAKE)" \
		-S rospovm -B "$(DIR_ROSPOVM_WASM_BUILD)" \
		-DQT_HOST_PATH="$(QT_NATIVE)" \
		$(WASM_CMAKE_ARGS)
	$(WASM_RUN) $(CMAKE) --build "$(DIR_ROSPOVM_WASM_BUILD)" \
		--target rospovm_html_minimal --parallel $(NPROC)
		
run: $(ROSP_FULL) $(DIR_ROSPOVM_BUILD)/rospovm_qt
	$(DIR_ROSPOVM_BUILD)/rospovm_qt $<

run_minimal: $(ROSP_FULL) $(DIR_ROSPOVM_BUILD)/rospovm_minimal
	$(DIR_ROSPOVM_BUILD)/rospovm_minimal $<

run_headless: $(ROSP_FULL) $(DIR_ROSPOVM_BUILD)/rospovm_headless
	$(DIR_ROSPOVM_BUILD)/rospovm_headless $<

report: tools/report.py
	$(PY) tools/report.py

benchmark:
	$(PY) tools/benchmarking/run_all.py --repeat $(BENCH_REPEAT)

benchmark_plot:
	$(PY) tools/benchmarking/plot_benchmarks.py

vm_fuzz_harness: $(DIR_ROSPOVM_BUILD)/Makefile
	$(CMAKE) --build $(DIR_ROSPOVM_BUILD) --target rospovm_fuzz_harness -j $(NPROC)

test: vm_fuzz_harness
	ROSPOS_VM_FUZZ_HARNESS=$(DIR_ROSPOVM_BUILD)/rospovm_fuzz_harness \
	$(PY) -m unittest discover -s tests -p "test_*.py" -v --buffer

dump: $(ROSP_FULL)
	$(HEXDUMP) $< 1>&2

build: bm compile frontend frontend_minimal vm_headless

format:
	black .
	isort .

min_run: $(ROSP_FULL) $(DIR_ROSPOVM_BUILD)/rospovm_minimal
	$(DIR_ROSPOVM_BUILD)/rospovm_minimal $<
clean:
	rm -rf $(DIR_ROSPOS_BUILD)
	rm -rf $(DIR_ROSPOVM_BUILD)
	rm -rf $(DIR_ROSPOVM_WASM_BUILD)
	rm -f $(HTMLDOCS)
	rm -f $(PDFDOCS)
	rm -f rospos/font_bitmap.bin
	rm -f rosbdump.txt
	rm -f $(ROS_ASM)
	rm -f $(ROSP_VARIANTS)

everything: build doc benchmark benchmark_plot report
