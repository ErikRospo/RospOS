PY := rospoas/venv/bin/python
HEXDUMP := hexdump -C
ROSPCC_PARSER := rospocc/parser.py

.PHONY: all bm parse compile dump build run

all: build

rospos/font_bitmap.ros: generate_fb_map_data.py
	mkdir -p $(dir $@)
	$(PY) generate_fb_map_data.py > $@

rospos/build/rospos.ros: rospocc/first_test.rosc rospocc/parser.py
	mkdir -p $(dir $@)
	$(PY) $(ROSPCC_PARSER) --input rospocc/first_test.rosc --output $@ 1>&2

rospos/build/rospos.rosp: rospos/build/rospos.ros rospoas/compile.py
	mkdir -p $(dir $@)
	$(PY) rospoas/compile.py --input $< --output $@ 1>&2
	$(HEXDUMP) $@ 1>&2

bm: rospos/font_bitmap.ros
parse: rospos/build/rospos.ros
compile: rospos/build/rospos.rosp

dump:
	$(HEXDUMP) rospos/build/rospos.rosp 1>&2
build: bm parse compile dump

run: build
	$(MAKE) -C rospovm -j8
	./rospovm/rospovm ./rospos/build/rospos.rosp --verbose --step
