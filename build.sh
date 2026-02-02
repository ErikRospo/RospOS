#!/bin/bash
set -euvo pipefail
source rospoas/venv/bin/activate
python3 rospoas/compile.py --input rospos/main.ros --output rospos/build/rospos.rosp 1>&2
hexdump -C rospos/build/rospos.rosp 1>&2
cd rospovm
make -j8 1>&2
cd ..
./rospovm/rospovm ./rospos/build/rospos.rosp --verbose