# OpenSees planar failure stopping and original attempt records

Source `b6b09430702ab253482a8cb074e4741ecbf9060b` changes the three planar
load-control paths in the external reference driver. Each path now stops at its
first nonzero `analyze(1)` return. The former four-call loop would attempt the
same target again after OpenSees reverted a failed step. That implicit retry is
removed. Model inputs, four quarter-load targets, iteration limits, original
convergence thresholds, comparison tolerances and reference values are unchanged.

The driver emits per-attempt target, previous and achieved load factor, return
code, analyze-call elapsed nanoseconds, and the original convergence-test counter
and norm array. Reported counters are not independently counted Newton or linear
solves. Other external paths retain their existing behavior. The receipt still
rejects a nonzero external return even if its numeric metrics match. Its existing
execution-output schema retains stdout/stderr hashes, not these attempt rows;
the original stdout and rows are retained in this observation packet. General
receipt-side raw-output retention remains separate work.

## Fresh pinned-runtime execution

The verified OpenSeesPy/OpenSeesPyLinux 3.7.1.2 runtime again reports OpenSees
3.7.1. All 24 extracted runtime files match the earlier sealed inventory before
and after execution. All 596 selected product/driver/test files match their Git
blobs and remain unchanged during this observation.

The complete updated driver executes once in a fresh process. All **35 recorded
analyze calls return zero**, including the 12 planar calls. Removing the new
attempt-telemetry field leaves a payload exactly equal to the entire earlier
fresh-driver payload. All three planar paths record the accepted load factors
0.25, 0.5, 0.75 and 1.0. This confirms unchanged numerical outputs for these inputs;
it does not make their earlier two reaction comparisons pass.

A separately declared failure diagnostic extracts the two original member-feature
and settlement blocks and changes only `NormUnbalance` to `1e-12 kN`. This repeats
the previously known failing configuration specifically to test the changed stop
behavior. Each case now makes **one** analyze call, returns **-3**, and retains
load factor zero after reversion. There are two failed calls in total, without
retry or subsequent target attempts. Their zero/reverted outputs are excluded
from physical comparisons. Both raw test counters report 81; that is retained as
reported, not promoted to verified Newton work.

| Execution | Parent seconds | Added planar analyze-call seconds |
| --- | ---: | ---: |
| Complete normal driver | 0.051848071 | 0.000115606 |
| Two-case failure diagnostic | 0.068875580 | 0.000403497 |
| Transformation availability probe | 0.082991139 | no analysis |

Per-call timings are nested inside process time. These are single local timing
observations, not speedup or hardware qualification. Preparation, source hashing,
upstream retrieval and audit/sealing costs are not included in those process
times. The initial preparation attempt failed before launching an external child
because it assumed the wrong earlier inventory filename suffix. Its retained
script and failure observation remain separate; its elapsed time is unknown.

## Why Corotational02 is not a demonstrated 2D remedy

The [official documentation](https://opensees.github.io/OpenSeesDocumentation/user/manual/model/geomTransf/Corotational02.html)
describes Corotational02 as the successor to the original transformation. The
actual pinned Python runtime rejects that name as unknown, before any element or
analysis exists. Both the initial interactive probe and the later captured
availability probe fail; neither performs a solver call.

More specifically, at inspected upstream revision
`2890cb36f59b5a707c607c63a831606f325adb7c`, the
[runtime command's 2D branch](https://github.com/OpenSees/OpenSees/blob/2890cb36f59b5a707c607c63a831606f325adb7c/SRC/runtime/commands/modeling/geomTransf.cpp#L404)
maps both names to `CorotCrdTransf2d` for three DOFs. That
[class still computes axial extension as `Ln - L`](https://github.com/OpenSees/OpenSees/blob/2890cb36f59b5a707c607c63a831606f325adb7c/SRC/coordTransformation/CorotCrdTransf2d.cpp#L406).
The legacy Tcl command accepts only the older name in this branch. These three
original source files and their GitHub API responses are retained with their
exact revision and hashes. This rules out a transformation-name substitution as
an evidenced correction for these two 2D cases; it does not assess all newer
OpenSees builds or 3D formulations. No replacement binary is built or installed.

## Verification, preservation and remaining scope

Twelve focused tests execute the three actual embedded planar model blocks with
injected success or failure at the first, middle or last call. They verify exact
attempt counts, reverted factors, original norms/counters and rejection through
the real receipt gate even when numeric metrics match. The initial valid selection
passes **17 tests in 7.36 s**, including five physical equilibrium regressions.
After adding the direct receipt-gate assertion, the final 12 driver tests pass in
0.62 s. Ruff, new-test formatting and diff checks pass. An earlier command names a
nonexistent test file and exits during collection; no tests execute in that attempt.

After the observer and all three child processes disappear, the observation at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-opensees-stop-lvd5ha08`
is inventoried and reread: **24 files / 490,002 bytes**, inventory SHA-256
`fa16998647162e542c118a4d81e0144bf5dd6bf6c1b8b9a53aed448c3907e6f7`.
The failed preparation packet retains six files / 188,455 bytes with inventory
SHA-256 `134e5d23688d37a3c6b3adc7d995446efd6671dbf2f96d5c0bae6aee7d2ca833`.
The [machine summary](opensees-planar-attempts-20260910.summary.json) binds both.

No new product reanalysis or full OpenSees/CalculiX receipt generation occurs in
the external observation. The five local product tests have their own test cost.
The [earlier two reaction mismatches](planar-fresh-reference-20260910.md), current
CI prerequisites, independent validation and the full M1-M5/P1-P3/R1-R2 roadmap
remain open. Protected receipts, product arithmetic and acceptance gates are
unchanged. Further reference work needs evidence of adequate 2D arithmetic and
convergence accuracy, rather than another name change or identical failed run.
