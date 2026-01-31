#!/bin/bash
set -e
source rospoas/venv/bin/activate
python3 rospoas/compile.py --input rospoas/test.ros --output rospovm/test.rosp
cd rospovm
make -j8
./main ./test.rosp