# RospoAS Refactor Plan

This document records the refactor plan and will be kept in the repository as a checkpoint and reference during the reimplementation.

Goals
- Replace ad-hoc dict-shaped AST with a small typed IR
- Introduce a clear pipeline: transform → lower → layout/relocations → encode → emit
- Centralize encoding, maps and validation
- Avoid in-place mutation across passes; make pipeline stages pure (return new IR)
- Add test coverage for lowering, layout and encoding

Pipeline (high level)
1. Parse: produce initial parse tree (unchanged Lark usage)
2. Transform: produce typed IR (dataclasses) and collect lifted constants
3. Lower: expand pseudo-instructions and produce relocation records where needed
4. Layout: compute section addresses & symbol table iteratively until stable
5. Encode: resolve relocations into immediates and produce bytes for each segment
6. Emit: write ROSP binary with header and segments

Key design choices
- Use explicit Immediate kinds (Value, Label, LabelPart, Lifted) to eliminate ad-hoc dict shapes.
- Keep Relocation records that point at instruction indices + field to patch; do not mutate original IR nodes.
- Centralize opcode maps and range validation in one module (`rospoas/encoding.py` planned).
- Provide small compatibility helpers to convert existing dict-shaped instructions into the new IR to ease incremental transition.

Files to be added/changed (plan)
- `rospoas/ir.py` — typed IR dataclasses and converters (created first)
- `rospoas/encoding.py` — centralized maps & encoding helpers
- `rospoas/transformer.py` — return IR objects instead of dicts
- `rospoas/lower.py` — lowering/pseudo-expansion (pure)
- `rospoas/layout.py` — layout & symbol resolution (iterative)
- `rospoas/encode.py` — final encoding & relocation application
- `compile.py` — orchestrate the new pipeline (minimal top-level changes)
- `tests/` — unit and integration tests, plus CI script using `./build.sh &> results.txt`

How to test locally
- Full build (integration):

```bash
./build.sh &> results.txt
```

Next steps
- Implement `rospoas/ir.py` (typed IR and converters) — done first
- Centralize encoding maps and helpers
- Update transformer to produce IR

Keep this file updated as the refactor progresses.
