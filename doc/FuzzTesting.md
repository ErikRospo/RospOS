# Fuzz testing

`make test` runs bounded Hypothesis tests for RospoAS, RospoCC, and the VM. The
normal profile uses 40 examples per generated test and a deterministic example
order. Failures include a reproducible Hypothesis example in the test output.

For a longer local campaign, run:

```sh
HYPOTHESIS_PROFILE=fuzz make test
```

The `fuzz` profile uses 1,000 examples per generated test. VM programs run in
the in-process VM core through the small test harness and are limited to 32
instructions per case; the Python driver also applies a five second process
timeout.
