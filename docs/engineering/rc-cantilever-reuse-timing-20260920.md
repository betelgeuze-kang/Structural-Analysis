# Retained reuse: constant-axial cantilever reversal path

Source `e7b5e2e2856671991784a3a5aef52f0c34d79307`. This extends the
L-frame observation to the existing public single-member cantilever, with
600 kN constant compression and seven transverse targets:
[-0.001, -0.002, -0.003, 0.001, 0.003, -0.001, -0.003] m.
Retained arithmetic and original terminal polishing were explicitly enabled.
Two repetitions reverse baseline/reuse execution order. Phase timing is on in
both arms; whole-benchmark times include recording, verification and serialization.
No learned policy, default promotion or independent physical validation follows.

The first setup attempt omitted terminal polishing and was rejected before any
benchmark by `twofold terminal coordinates require enabled original polishing`.
It remains at `structural-cantilever-reuse-kv0nocc8` under the evidence mount.
A separate request enabled that prerequisite; targets and tolerances were unchanged.
The valid study completed all four benchmarks, each containing four paths and
32 steps (preload plus seven targets per path): 16 paths, 128 steps total.
A separate saved-artifact audit re-read original step bytes and full-history
reports, recounted dispatches and checked committed material states.

| Ordered repetition | Baseline seconds | Reuse seconds | Reuse / baseline |
|---|---:|---:|---:|
| baseline first | 1.837798786 | 1.720044597 | 0.9359265063 |
| reuse first | 1.818127471 | 1.718101489 | 0.9449840654 |

All original baseline/reuse step bytes match. Fresh-reference repeats and all
history comparisons pass. Each benchmark reduces actual Newton dispatches from
162 to 146, with 16 recorded reuse hits. The directory label `constant-False`
reflects the supplied-case loop variable, not the actual request: the request
contains one constant load and the summary correctly reports `constant=true`.

Maximum recorded tensile damage, compressive damage and accumulated plastic
strain are all zero across accepted checkpoints. This is an elastic-material
path through the nonlinear solver, not material-active or yielded validation.
Two short repetitions do not establish a generalized speedup or learned benefit.
The failed binary64 L-frame study remains failed. Material-active multi-case
coverage and independent validation remain open.

Original inputs, predeclared plan, execution log/receipt, results and independent
artifact-audit script are at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cantilever-reuse-15w9478s`.
The external inventory covers 821 files; all listed hashes were re-read.
Inventory SHA-256:
`c8ed2a656d7a0e2e12159b17ddd2b7223a51fe55a5c86beae926552663ec9f4b`.
