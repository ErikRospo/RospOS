"""Shared Hypothesis profiles for the normal test suite and longer fuzz runs."""

import os

from hypothesis import settings

settings.register_profile("normal", max_examples=40, deadline=None, derandomize=True)
settings.register_profile("fuzz", max_examples=1000, deadline=None, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "normal"))
