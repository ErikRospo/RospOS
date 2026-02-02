#!/bin/bash
set -euvo pipefail
source rospoas/venv/bin/activate
python3 rospoas/compile.py --input rospoas/test.ros --output rospovm/test.rosp
cd rospovm
make -j8
hexdump -C test.rosp
./main ./test.rosp debug