# Immediate line-search assembly reuse: bounded experiment

The serial research runner reduced actual Newton assembly dispatches from 1,104
to 976 (128 fewer, 11.59%) while preserving all 224 paired native step files byte
for byte. Across 16 order-balanced comparisons, aggregate whole-benchmark time
was 5.94% lower. This is a deterministic optimization observation on one authored
small L-frame, not an AI gain, an independent physical validation, or a general
performance guarantee. Default solver behavior is unchanged.

## Mechanism and boundaries

`_vector_line_search()` computes residual and tangent but discards the tangent;
the next primary Newton iteration assembles again at the accepted coordinates.
The runner temporarily wraps `newton.assemble_vector` in its own serial process.
It retains one result only for the exact RC displacement-control adapter type,
and consumes it only on the immediately following primary iteration with the
same adapter object, dtype, shape, and coordinate bytes. Copies prevent result
aliasing. Any intervening dispatch, changed coordinate, compensation, exception,
or different adapter invalidates the entry. Terminal, final, and blocked
observations are fresh. No tolerances, material laws, Newton decisions, accepted
checkpoints, or final verification rules are changed.

The actual-dispatch recorder is called only for real assemblies. Reuse hits have
a separate experiment count. This does not count element/material operations or
assemblies outside Newton. The experiment is not safe for a concurrent service:
its temporary module patch is a research harness, not a supported solver option.
Reports inside this packet must be interpreted with the enclosing experiment
manifest; they are not ordinary baseline performance receipts.

## Executed comparison

Base revision: `6316cd010b48cca2dcd77d4bc17656f6d5f106b7`, plus the source-hashed
research runner. The supplied revision in the underlying reports identifies that
base, not an attestation that the experimental wrapper is in that commit.

Model: `examples/public_rc_fiber_frame_l_frame_material_history.json`.
Control DOF 7, targets `[-1e-6, -2e-6, 1e-6]` m, reversals enabled, terminal
polishing enabled. The constant-load variants add N3 vertical load -0.1 kN.
Binary64 and the existing retained arithmetic profile are compared separately.
The proposal callback is deterministic secant; no policy is fitted.

Four repetitions per configuration alternate baseline-first and reuse-first.
Each benchmark executes reference, secant, proposal, and fresh-reference paths.
There are 32 benchmarks, 128 complete paths, and 448 actual step executions,
forming 224 byte-exact step pairs. These are repeated observations of one model,
not independent structures or physical specimens. Full-history comparison
reports also match across both executions.

| Arithmetic | Constant preload | Dispatches per benchmark, baseline → reuse | Whole-benchmark time reduction, four repetitions pooled |
| --- | --- | --- | --- |
| Binary64 | No | 52 → 44 | 6.64% |
| Binary64 | Yes | 72 → 64 | 3.80% |
| Retained | No | 64 → 56 | 8.15% |
| Retained | Yes | 88 → 80 | 5.06% |

All 16 paired wall-time ratios were below one (range 0.9130–0.9745). The aggregate
ratio is 0.9405528155, a ratio of summed wall times, not an inference confidence
interval. Time includes full benchmark execution, serialization, verification,
recorder overhead, cache lookup and copying. The host was not isolated; four
repetitions and this small displacement range do not establish nonlinear
hard-case, large-model, or production speedup. Reduced dispatch count is the
stronger deterministic finding.

## Verification and reproduction

The focused boundary suite passed **11 tests**: one-use copying, recorder
dispatches, exact adapter identity/type, coordinate/dtype/signed-zero changes,
compensated calls, mandatory observations, and exception preservation. Ruff and
diff checks passed. The real experiment above supplies numerical/path evidence;
the unit tests alone do not.

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 scripts/diagnose_rc_control_line_search_reuse.py \
  /absolute/new/output-directory --repetitions 4
```

The destination must not exist. Retained raw packet: 2,981 files, 146,526,497
bytes. Its adjacent inventory was independently reread and checked; SHA256
`56550511160bba74ae886f9d22bff01c5c3abf69be6212b47717a3c5318df039`.
Exact paths, runner/model hashes, group statistics and counts are in
[the summary](rc-line-search-reuse-20260912.summary.json).

## Consequence for the roadmap

This identifies measurable work reduction without fitting another model to
previously negative labels. Before exposing a supported opt-in implementation,
verify immutable-parent assumptions explicitly, include materially nonlinear
paths and failure cases, and repeat full-history/cost comparisons. AI must then
be compared with the improved deterministic baseline as well. Learned net
benefit, full hosted qualification, and independent physical acceptance remain
open. This experiment does not resolve the external-reference CI blockers.

The [yield/unload follow-up](rc-yielded-reuse-20260912.md) extends this observation
to positive committed steel plastic memory and retains a separate binary64
baseline comparison failure without assigning it a speed ratio.
