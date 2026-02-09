#!/bin/bash
set -euvo pipefail
source rospoas/venv/bin/activate
python generate_fb_map_data.py > rospos/font_bitmap.ros
python rospocc/parser.py 1>&2
cp rospocc/out/generated.ros rospos/build/rospos.ros
python3 rospoas/compile.py --input rospos/build/rospos.ros --output rospos/build/rospos.rosp 1>&2
hexdump -C rospos/build/rospos.rosp 1>&2
exit
cd rospovm
make -j8 1>&2
cd ..
./rospovm/rospovm ./rospos/build/rospos.rosp --verbose --step