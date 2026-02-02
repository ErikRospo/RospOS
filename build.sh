#!/bin/bash
set -euvo pipefail
source rospoas/venv/bin/activate
python3 rospoas/compile.py --input rospos/main.ros --output rospos/build/rospos.rosp
hexdump -C rospos/build/rospos.rosp
cd rospovm
make -j8
cd ..
./rospovm/rospovm ./rospos/build/rospos.rosp debug