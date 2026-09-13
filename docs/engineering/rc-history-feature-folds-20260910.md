# Normalized accepted-history warm starts: retained negative result

Source `0c23f2d5d51e6f477a7e513a16606c62b4cbb501` adds the optional
`length-normalized-accepted-control-history.v1` feature profile. The existing
learning-study default and v1/v2 policy formats remain supported. The explicit
v3 policy binds the new layout, arithmetic profile and load-coordinate scale.
Runtime proposals still require matching solver/context/DOF identities, fitted
feature ranges, finite coordinates and subsequent reference-solver acceptance.
No acceptance tolerance, protected receipt or production default changes.

Spatial coordinates, including scaled rotations, use the model's declared
rotation-coordinate length. The augmented load coordinate uses the request's
separate length scale. Geometry, fiber offsets/areas and reference loads are
scaled by their declared length powers. Forces divided by length squared and
moments divided by length cubed are not dimensionless. This profile does not
claim invariance to arbitrary numerical rotation-scale changes.

Eight features describe only the already accepted control history: extrema,
travel, reversal count, current branch direction, last reversal, branch travel
and next prescribed direction. The previous absolute accepted-step count is
removed. No future response or material trial supplies an input. Normalized
correction targets retain the exact original coordinate correction and scales;
proposal and diagnostic paths convert predictions back to solver coordinates.

## Fixed comparison on the existing 964 training pairs

The observer checks the original expanded-study inventory and copies only its
training samples, policy and input plan. The plan contains evaluation metadata;
only training-case declarations are decoded, and no validation/holdout response
samples are read. Original feature vectors and secant corrections are reproduced
before deriving each new row. Every derived row retains its original sample hash,
accepted coordinates and source correction. The decoded training requests share
the original policy's solver-config hash and load-coordinate scale `0.001 m`.

One fit uses all 964 pairs to create a separate candidate policy. Four further
fits each use 723 pairs and withhold 241 from one complete authored training
case. All use the predeclared ridge `1e-6` and OOD margin `0.1`; no hyperparameter
search or automatic retry occurs. The previous sealed legacy-fold report is
reused without refitting. The secant RMSE arrays are exactly equal between the
old and new diagnostics in their original coordinate order.

| Withheld case | Eligible rows, old / new | New learned/secant RMSE range | New learned/old learned RMSE range |
| --- | ---: | ---: | ---: |
| train-a | 0 / 0 | 0.998-6.379 | 0.936-3.667 |
| train-b | 241 / 241 | 1.157-1.458 | 0.746-1.411 |
| train-c | 0 / 0 | 0.876-1.641 | 0.830-1.138 |
| train-d | 0 / 0 | 1.736-8.323 | 0.487-1.587 |

Each range spans six separate non-controlled augmented coordinates; it is not
an aggregate across different units. Values above one are worse. The prescribed
coordinate is excluded because its correction is reset at runtime. Results for
range-ineligible rows are ungated diagnostics, not admissible proposals.

The sole eligible case still has greater error than secant in all six compared
coordinates. Feature-range coverage does not improve. Normalization removes the
old standalone rotation-length violation for train-a but creates out-of-range
normalized reference load and fiber geometry values for all its rows. In train-d,
normalized geometry, reference load and fibers remain out of range. This is a
negative result for the combined normalization/history profile, not evidence
that history features alone are ineffective: their effects were not isolated.
No net runtime or independent physical improvement is established.

The candidate remains experimental and is not promoted. These findings do not
justify another expensive full-path evaluation of this unchanged candidate.
Further work must address model representation and independently diverse physical
cases; simply changing units or adding history did not resolve transfer here.
Public experiments still need material/reinforcement/loading/sensor correspondence
before admission. An independent campaign split cannot be manufactured by
partitioning rows from this four-case authored project.

## Costs and verification

The observed study performs **five fits and zero structural solver calls**.
Derivation takes 1.380070065 s and the full-training fit 0.009162606 s. Four fold
fits take 0.006821077, 0.006457337, 0.006472096 and 0.006353185 s, nested in a
0.440552405 s fold diagnostic. Worker time through report writing is
3.108147384 s; parent time including interpreter/import overhead is 4.606692664 s.
Peak worker RSS is 335,720 KiB. Source verification, parent-side final audits,
sealing, documentation and GitHub operations are outside those intervals.

The initial five-file selection passes 74 tests in 48.75 s, including actual
small train/fit/evaluation paths, retained arithmetic, legacy policies and source
split guards. After adding a malformed-row guard and a focused derivation test,
19 feature/fold tests pass in 1.68 s. The new test verifies original-unit error
reporting, source-label preservation, tampered accepted-coordinate rejection and
unchanged fold policies when that fold's withheld inputs/labels change. These
selections overlap; they are not 93 distinct tests. Three-source mypy, Ruff and
diff checks pass. Small synthetic fixtures do not establish real-world accuracy.

All 599 selected source/test files match Git before and after the observation.
Original input copies and source artifacts retain their hashes. Observer and
worker processes are confirmed absent before sealing the packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-history-folds-1qao5ssc`:
**15 files / 58,633,830 bytes**, inventory SHA-256
`8358e827821738bb718e858db5fe72fee0f40b99cb7a77051cc8ced3d46570ce`.
The packet contains the protocol, observer/worker, original inputs, derived
samples, candidate and four fold policies, reports and process outcomes. All
files are reread exactly. The [machine summary](rc-history-feature-folds-20260910.summary.json)
retains every coordinate ratio, range violation and cost. This local observation
does not close hosted CI, independent verification or the full roadmap.

The preceding published head `e21287c43703dd168a8051c9167dc82713d8b52b`
finishes main CI [34387415218](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34387415218)
and all four repository-test shards in
[34387415269](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34387415269)
with failures in `Materialize exact current-source test evidence`. All five
original job logs name `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. The repository tests do not
run past that prerequisite. The separate CI packet retains their completed
run/job metadata and raw logs; its inventory is in the machine summary. This
confirms the existing external-replay prerequisite, not a new test assertion
failure or permission to bypass the gate. Current-source hosted acceptance
remains pending.
