PY := rospoas/venv/bin/python
HEXDUMP := hexdump -C
ROSPCC_PARSER := rospocc/parser.py
DOCS := Design.md Ideas.md Log.md

# Build directories
DIR_ROSPOS_BUILD := rospos/build
DIR_DOCS_BUILD := build


# Ensure build directory exists (order-only dependency)

HTMLDOCS := $(DOCS:.md=.html)
PDFDOCS := $(DOCS:.md=.pdf)

.PHONY: all bm parse compile dump build run clean doc transpiler

all: build

$(DIR_ROSPOS_BUILD):
	mkdir -p $(DIR_ROSPOS_BUILD)
$(DIR_DOCS_BUILD):
	mkdir -p $(DIR_DOCS_BUILD)
	
rospos/font_bitmap.ros: generate_fb_map_data.py
	mkdir -p $(dir $@)
	$(PY) generate_fb_map_data.py > $@

rospos/build/rospos.ros: rospocc/first_test.rosc rospocc/parser.py | $(DIR_ROSPOS_BUILD)
	$(PY) $(ROSPCC_PARSER) --input rospocc/first_test.rosc --output $@ 1>&2

rospos/build/rospos.rosp: rospos/build/rospos.ros rospoas/compile.py | $(DIR_ROSPOS_BUILD)
	$(PY) rospoas/compile.py --input $< --output $@ 1>&2
	$(HEXDUMP) $@ 1>&2
	
build/%.html: doc/%.md | $(DIR_DOCS_BUILD)
	pandoc $< --filter pandoc-include -s -o $@
	sed -i 's/max-width: 36em;/max-width: 64em;/g' $@ 
# The above sed command is a hack to increase the max width of the content in the generated HTML.
# Pandoc's default CSS sets a max-width of 36em, which can make the content look narrow on larger screens.
# By changing it to 64em, we allow the content to take up more horizontal space, improving readability on wider displays.


build/%.pdf: doc/%.md | $(DIR_DOCS_BUILD) 
	pandoc $< --filter pandoc-include -V links-as-notes=true -o $@

transpiler: 
	$(MAKE) -C rospocctranspiler -j8
	$(PY) rospoas/compile.py --input rospocctranspiler/riscv_transcompiler.ros --output rospocctranspiler/riscv_transcompiler.rosp 1>&2
	
doc: $(addprefix build/,$(HTMLDOCS)) $(addprefix build/,$(PDFDOCS))

bm: rospos/font_bitmap.ros
parse: rospos/build/rospos.ros
compile: rospos/build/rospos.rosp

dump: rospos/build/rospos.rosp
	$(HEXDUMP) $< 1>&2
build: bm parse compile dump

run: build
	$(MAKE) -C rospovm -j8
	./rospovm/rospovm ./rospos/build/rospos.rosp --verbose --step

clean:
	rm -rf rospos/build
	rm -rf rospovm/build
	rm -rf build/*.html
	rm -rf build/*.pdf
	rm -rf rospos/font_bitmap.ros
	$(MAKE) -C rospovm clean