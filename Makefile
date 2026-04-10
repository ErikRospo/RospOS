PY ?= rospoas/venv/bin/python
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
ROSPOAS_VERBOSE_ARG := $(if $(VERBOSE),--verbose,)

ROSPOAS_DEP := $(sort $(shell find rospoas -maxdepth 1 -type f))
ROSPCC_DEP := $(sort $(shell find rospocc -maxdepth 1 -type f))
ROSPOS_DEP := $(sort $(shell find rospos -type f -not -path "rospos/build/*"))
ROSPOVM_SRC := $(sort $(shell find rospovm -type f -not -path "rospovm/build/*"))

.DEFAULT_GOAL := build

.PHONY: all help bm parse compile dump build clean doc format frontend \
		frontend_cmake run vm_headless run_headless test report \
		benchmark benchmark_plot everything frontend_minimal run_minimal \
		min_run

all: build

help:
	@echo "Common targets:"
	@echo "  bm               Generate font bitmap binary"
	@echo "  parse            Compile .rosc to .ros"
	@echo "  compile          Assemble all .rosp output variants"
	@echo "  frontend         Build Qt VM frontend"
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
	$(PY) $(ROSPCC_PARSER) --input $< --output $@ 1>&2

define make_rosp_variant
$1: $(ROS_ASM) $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) $(ROSPOAS_COMPILE) $(ROSPOAS_COMMON_ARGS) $(ROSPOAS_VERBOSE_ARG) $2 --input $$< --output $$@ 1>&2
endef

$(eval $(call make_rosp_variant,$(ROSP_FULL),--debug-all))
$(eval $(call make_rosp_variant,$(ROSP_DEBC),--compress-debug))
$(eval $(call make_rosp_variant,$(ROSP_BINC),--compress-bin))
$(eval $(call make_rosp_variant,$(ROSP_COMBINED),--compress-bin --compress-debug))

$(DIR_ROSPOVM_BUILD)/Makefile: rospovm/CMakeLists.txt $(ROSPOVM_SRC) | $(DIR_ROSPOVM_BUILD)
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

test:
	$(PY) -m unittest discover -s tests -p "test_*.py" -v

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
	rm -f $(HTMLDOCS)
	rm -f $(PDFDOCS)
	rm -f rospos/font_bitmap.bin
	rm -f rosbdump.txt
	rm -f $(ROS_ASM)
	rm -f $(ROSP_VARIANTS)

everything: build doc benchmark benchmark_plot report