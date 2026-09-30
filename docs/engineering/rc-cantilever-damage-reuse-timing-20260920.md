# Retained reuse on a concrete-damaging constant-axial reversal path

Source `d21c2bc7d7d0900caa6702ec6a9ed1e8a7cf6484`. Following the elastic-state
cantilever observation, the same public model and 600 kN constant compression
were used with predeclared targets [-0.004, -0.008, -0.016, 0.008, 0.016,
-0.008, -0.016] m. Retained arithmetic, original terminal polishing and phase
timing were explicitly enabled in both arms. Two repetitions reversed execution
order. No tolerances, constitutive parameters or production defaults changed.

Four benchmarks contain 16 full paths and 128 steps including preload. Separate
artifact auditing checks every full-history pass, fresh-reference repeat, original
step-byte equality and dispatch accounting. Baseline/reuse steps match exactly;
corresponding arms also match across repetitions. The audit finds maximum
accepted concrete tensile damage 0.9855127936819933, compressive damage zero,
and accumulated steel plastic strain zero. This is a concrete-damaging path,
not evidence of steel yielding, mesh convergence or physical calibration.

| Repetition | Order | Baseline seconds | Reuse seconds | Time ratio |
|---|---|---:|---:|---:|
| 0 | baseline, reuse | 2.928907495 | 2.335782232 | 0.7974926610 |
| 1 | reuse, baseline | 2.918794026 | 2.313962924 | 0.7927804783 |

Each benchmark has 332 baseline actual Newton dispatches and 238 with reuse,
plus 94 recorded reuse hits. Whole-benchmark time includes serialization,
verification and recording. Observed reductions are 20.25% and 20.72%; the
whole subprocess took 11.950456047 seconds. Audit/inventory time is outside
these timings. Two short repetitions on one authored path do not establish
statistical or general speedup. The optional mechanism is deterministic,
not an AI gain. Prior binary64 failure and independent validation requirements
remain unchanged. Together with the L-frame study this adds a distinct geometry
and constant-load condition; it does not close broad nonlinear runtime coverage.

Inputs, prior plan, log, run receipt, original results, audit and scripts:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cantilever-active-reuse-5npn0bxx`.
All 821 inventory-listed files were re-read for SHA-256 verification. The external
inventory SHA-256 is
`9645899682e860ce42c2321321dc3fedd6e898e30e14b48664301946f94a6a7c`.
The source model hash is
`b642e14a56ca88b74dfbbb6749f7b4b87199ef1aafb94c5265ec35b89eab7968`;
the request hash is
`7b1892d1f14ae884e2afee366cc2304ed718acefa8260e2272f8677404ae703b`.
