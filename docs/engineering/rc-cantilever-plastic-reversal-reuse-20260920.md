# Plastic reversal: failed large increments and a separate subdivided path

Source `ae9be57656e8922d9066e7de8012bb63e2b0a64e`. Both studies use the
existing public cantilever, 600 kN constant compression, retained arithmetic,
original terminal polishing and phase timing. Constitutive parameters, tolerances
and solver defaults are unchanged. These are authored internal experiments,
not independent physical validation or learned-policy benefits.

## Original requested path fails before reuse

Targets in mm: [-8, -16, -32, -48, 16, 32, 48, -16, -32, -48].
The initial baseline benchmark runs reference, secant, identical-secant proposal
and fresh reference. All accept four targets, then fail target index 4 (+16 mm)
with `line_search_failed_to_reduce_residual`; rollback is exact in all four.
Reference/fresh relative equilibrium is 0.5595539951876086, versus
0.5427549366958281 for secant/proposal. No reuse benchmark or second repetition
executes. Full-path comparison and reference-repeat flags are false because
paths are incomplete; this does not establish nondeterministic execution.

Maximum committed tensile damage is 0.9999936965622573 and accumulated steel
plastic strain 0.002743704718410003; compressive damage stays zero. The failure
receipt preserves 2.609623843 seconds of benchmark wall time and binds the
original comparison bytes (SHA-256
`f2076be6261f45c43fea4e85db123fc6b13fc81e6b94cef90cbf025d41c85b61`).
Paired speed ratio remains null. This is a failed plastic reversal experiment.

## Subdivided requested path completes

A separate predeclared request traverses 0 to -48, then +48, then -48 mm in
8 mm increments: 30 targets, retaining every original target. This changes the
committed numerical history; it is not proof of equivalence to, repair of, or
step-size convergence for the failed request. Both paired arms use exactly this
same new request, and execution order is reversed on the second repetition.

Four benchmarks comprise 16 full paths and 496 steps including preloads.
All original baseline/reuse step bytes match, and corresponding arms match
across repetitions. Fresh-reference and all full-history comparisons pass.
A separate artifact audit recounts actual dispatches and committed states.
Maximum tensile damage is 0.999998898902848, accumulated steel plastic strain
0.009317078120152825 and compressive damage zero. Steel plasticity and concrete
softening are present; the coarse section discretization is not mesh-qualified.

| Repetition | Baseline seconds | Reuse seconds | Reuse / baseline |
|---|---:|---:|---:|
| baseline first | 9.773586966 | 8.017639361 | 0.8203374451 |
| reuse first | 9.768456730 | 8.035352099 | 0.8225815317 |

Each benchmark reduces actual Newton dispatches from 1,036 to 762, with 274
recorded hits. Whole-benchmark times include serialization, verification and
recording; the full subprocess took 37.072937525 seconds, excluding later audit
and inventory work. Two repetitions support only this bounded observation,
not broad speedup or a decision to enable reuse by default. Independent material
validation, load-step convergence and unseen-case learned benefit remain open.

## Retained evidence

Under `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/`:

- Failed original: `structural-cantilever-plastic-reuse-kayrmjss`, inventory SHA-256
  `ad9f1ed1092daef3d251339fbcfa891114defc40806d1f3af506f512c7dca297`.
- Subdivided: `structural-cantilever-substep-reuse-rzdfh0zq`, inventory SHA-256
  `8f2389bb947e9745d457cdc46ce51428e26c144a678b82588d9e09c72f529676`.

Each packet contains original inputs, pre-execution plan, log/receipt, results
and audit scripts. Listed hashes were re-read; the successful inventory contains
3,029 files. Failures were not overwritten or excluded from the record.
