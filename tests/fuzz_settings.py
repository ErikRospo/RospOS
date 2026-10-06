"""Shared logging and Hypothesis profiles for the test suite and fuzz runs."""

import os
import sys

from hypothesis import settings
from loguru import logger

# Loguru's default sink keeps the original stderr, bypassing both unittest
# buffering and the compiler helpers' redirects. Resolve stderr when logging
# instead, and keep compiler/assembler internals out of normal test output.
logger.remove()
logger.add(
    lambda message: sys.stderr.write(message),
    level="WARNING",
    format="{level}: {message}",
    backtrace=False,
    diagnose=False,
)

settings.register_profile("normal", max_examples=40, deadline=None, derandomize=True)
settings.register_profile("fuzz", max_examples=1000, deadline=None, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "normal"))
