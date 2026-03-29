PY := rospoas/venv/bin/python
HEXDUMP := hexdump -C
ROSPCC_PARSER := rospocc/parser.py
DOCS := Design.md Ideas.md Log.md

# Build directories
DIR_ROSPOS_BUILD := rospos/build
DIR_DOCS_BUILD := build/
ROSPOAS_ARGS := --optimize --bin-version 2 --rospocc-mapping --segment-debug
ROSPOAS_DEP := $(shell find ./rospoas -maxdepth 1 -type f)
ROSPCC_DEP := $(shell find ./rospocc -maxdepth 1 -type f)
ROSPOS_DEP :=  $(shell find ./rospos -type f -not -path "./rospos/build/*") 
ROSPOVM_DEP := rospovm/build/Makefile $(shell find ./rospovm -type f -not -path "./rospovm/build/*")
# Ensure build directory exists (order-only dependency)

HTMLDOCS := $(DOCS:.md=.html)
PDFDOCS := $(DOCS:.md=.pdf)

.PHONY: all bm parse compile dump build clean doc format frontend frontend_cmake run vm_headless run_headless test report benchmark everything

all: build

$(DIR_ROSPOS_BUILD):
	mkdir -p $(DIR_ROSPOS_BUILD)
$(DIR_DOCS_BUILD):
	mkdir -p $(DIR_DOCS_BUILD)
	
rospos/font_bitmap.bin: tools/generate_fb_map_data.py ./tools/font8x8_basic_data.h
	mkdir -p $(dir $@)
	$(PY) tools/generate_fb_map_data.py --output $@ --input ./tools/font8x8_basic_data.h 1>&2

rospos/build/rospos.ros: rospos/main.rosc $(ROSPCC_DEP) $(ROSPOS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) $(ROSPCC_PARSER) --input rospos/main.rosc --output $@ 1>&2

rospos/build/rospos.rosp: rospos/build/rospos.ros $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) rospoas/compile.py $(ROSPOAS_ARGS) --debug-all $(if $(VERBOSE),--verbose,) --input $< --output $@ 1>&2
rospos/build/rospos_debc.rosp: rospos/build/rospos.ros $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) rospoas/compile.py $(ROSPOAS_ARGS) --compress-debug --input $< --output $@ 1>&2
rospos/build/rospos_binc.rosp: rospos/build/rospos.ros $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) rospoas/compile.py $(ROSPOAS_ARGS) --compress-bin --input $< --output $@ 1>&2
rospos/build/rospos_c.rosp: rospos/build/rospos.ros $(ROSPOAS_DEP) | $(DIR_ROSPOS_BUILD)
	$(PY) rospoas/compile.py $(ROSPOAS_ARGS) --compress-bin --compress-debug --input $< --output $@ 1>&2

rospovm/build:
	mkdir -p rospovm/build

rospovm/build/Makefile: rospovm/CMakeLists.txt | rospovm/build
	cmake -S rospovm -B rospovm/build/
	
rospovm/build/rospovm_qt: $(ROSPOVM_DEP)
	mkdir -p $(dir $@)
	cmake --build rospovm/build/ -j $(shell nproc)

rospovm/build/rospovm_headless: $(ROSPOVM_DEP)
	cmake --build rospovm/build/ --target rospovm_headless -j $(shell nproc)


build/%.html: doc/%.md | $(DIR_DOCS_BUILD)
	pandoc $< --filter pandoc-include -s -o $@
	sed -i 's/max-width: 36em;/max-width: 64em;/g' $@ 
# The above sed command is a hack to increase the max width of the content in the generated HTML.
# Pandoc's default CSS sets a max-width of 36em, which can make the content look narrow on larger screens.
# By changing it to 64em, we allow the content to take up more horizontal space, improving readability on wider displays.


build/%.pdf: doc/%.md | $(DIR_DOCS_BUILD) 
	pandoc $< --filter pandoc-include -V links-as-notes=true -o $@

doc: $(addprefix build/,$(HTMLDOCS)) $(addprefix build/,$(PDFDOCS))

bm: rospos/font_bitmap.bin
parse: rospos/build/rospos.ros
compile: rospos/build/rospos.rosp rospos/build/rospos_debc.rosp rospos/build/rospos_binc.rosp rospos/build/rospos_c.rosp
frontend_cmake: rospovm/build/Makefile
frontend: rospovm/build/rospovm_qt
report: tools/report.py
	$(PY) tools/report.py

run: rospos/build/rospos.rosp | rospovm/build/rospovm_qt
	rospovm/build/rospovm_qt $<

vm_headless: rospovm/build/rospovm_headless

run_headless: rospos/build/rospos.rosp vm_headless
	rospovm/build/rospovm_headless $<

benchmark:
	$(PY) tools/benchmarking/run_all.py --repeat 100

test:
	$(PY) -m unittest discover -s tests -p "test_*.py" -v
dump: rospos/build/rospos.rosp
	$(HEXDUMP) $< 1>&2
build: bm parse compile frontend_cmake frontend vm_headless

format:
	black .
	isort .
clean:
	rm -rf rospos/build
	rm -rf rospovm/build
	rm -rf build/*.html
	rm -rf build/*.pdf
	rm -rf rospos/font_bitmap.bin
	
everything: build doc benchmark report 