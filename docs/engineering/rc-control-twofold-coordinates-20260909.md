# Experimental parent-increment RC control with native coordinate compensation

The exact-strain observation at `d81cd8e9033024afcd4f800e63217ecc9abbe091`
removed intermediate strain evaluation error but still failed all six fixed
reference/secant comparisons. The saved original-parent diagnostic located the
remaining section-moment differences in finite accepted coordinates. This next
experiment changes the representation used during an original solve and restart.
It does not modify saved forces or relax comparison tolerances.

The explicit `coordinate_precision="twofold-increment"` profile requires
`strain_evaluation="exact-rational"`. Original vector Newton solves an increment
from the native committed parent in generalized coordinate space. Each trial
forms parent high + parent low + Newton increment using rational intermediates,
then rounds high and residual low separately to binary64. FastTwoSum normalizes
the represented sum at rounding ties, and underflowed zeros are canonical positive
zeros. Physical scaling,
member transforms and exact Hermite strain evaluation carry both components.
Zero matrix coefficients are omitted from rational products. This is a bounded,
portable coordinate experiment; Newton vectors, Jacobians, linear solves,
constitutive values, final strains, forces and load factors remain binary64.
Increment rounding, two-component rounding and material/force rounding remain.
There is no general high-precision solver or independent physical validation.

Reference initialization is the zero increment from the native parent. Secant
and other caller proposals remain binary64 absolute initial estimates and are
converted into increments relative to that parent. No proposal owns the committed
state. The original Newton implementation and configured residual/increment,
equilibrium, control, parent-binding and rollback gates remain in use. The solver's
coordinate metric records its actual increment; separate response fields record
the reconstructed absolute high and low coordinates and parent origin. Recovery
replays the original increment against the original parent, repeats native
assembly and requires identical response/checkpoint bytes. Control errors use
both coordinate components. Load-factor origin is derived from the accepted
binary64 load factor; load-factor compensation is not persistent state.

The native checkpoint uses a distinct strict schema,
`stateful-fiber-frame2d-twofold-checkpoint.v1`, with free high/low arrays and
`stateful-fiber-beam2d-twofold-state.v1` local low arrays. Canonical coordinate
expansions, both components, material states and arithmetic profile identities
are hash-bound. Native restoration validates the rounded global projection,
exact local component transforms and exact coordinate-to-section strain binding.
Missing low data, noncanonical expansions (including negative-zero components),
malformed JSON, duplicate keys and mismatched profiles fail closed. A rehashed
free low-part change still fails its binding to saved element coordinates.
There is no mutable hidden coordinate cache required for continuation.

Default `coordinate_precision="binary64"` retains its prior contract/schema and
response shape for both matrix and exact-rational strain modes. The experiment
is selected by `benchmark_rc_control_seed_paths`; public API/CLI/Workbench and
learning admission do not select it. The ordinary load-step path has no twofold
adapter and cannot execute this experimental problem profile.

The focused checks exercise sub-ULP increments, cancellation under a coordinate
transform, independent 100-digit strain evaluation with a nonzero low component,
canonical pair rejection, native hash/schema rejection, forged original solver
metrics and exact rollback, and cyclic reference/secant/fresh-reference recovery.
A fresh interpreter restores a nonzero-low checkpoint and reproduces all remaining
step results and the final native checkpoint byte-for-byte. These checks establish
bounded implementation behavior, not successful 242-target error reduction.


## Completed source-bound observation
Frozen implementation `d2ecdaa25a5b1d68cab8508753a939bd3edfa870` completes six serial fresh processes,
18 paths and all 242 targets per path. The original invocation records account for
**4,356 core entries / 18,144 Newton and linear counts**.
All reference/fresh-reference histories and native checkpoints are exact; all
within-case/strategy repetitions are exact. All 18 terminal native checkpoints
reopen through the original strict codec and reproduce their canonical bytes.
The no-solve record audit checks all 415 frozen source/script/test files against
Git, unchanged input hashes against the preceding sealed inventory, original
Newton/assembly/parent gates, all accepted native high/low pairs reconstructed
from original parent plus original solver increment, and complete physical
comparisons. All 26,136 integration-point strains match a separate rational
Hermite expression using both saved local coordinate components.

**Secant passes 0/6 fixed physical comparisons.** The preceding exact-strain
binary64 failures remain negative evidence. The new coordinate profile reduces
some differences but does not establish a repaired solver or accepted acceleration.

| Geometry | Mismatches per repeat | Reference median / sample SD (s) | Secant median / sample SD (s) | Reference / secant Newton-linear counts per path |
| --- | --- | --- | --- | --- |
| base | [339, 339, 339] | 56.322093 / 0.468420 | 40.462766 / 0.390607 | 1155 / 761 |
| long | [262, 262, 262] | 53.415415 / 0.086446 | 39.633569 / 0.359381 | 1109 / 759 |

The base case retains 233 member-end-force, one section and 105 reaction
mismatches per repeat, with maximum mixed-SI difference 1.280568540096283e-9.
The longer case retains 179, one and 82 respectively, with maximum
9.313225746154785e-10. The preceding binary64 exact-strain observation had
1,425 / 1,428 total mismatches and 359 / 355 section mismatches per repeat.

All 3,399 accepted terminal corrections, 4,356 additional polishing
assemblies and 3,399 polishing solves are included in original
counts and elapsed time. Serial parent time is 934.746751 s.
Source staging, implementation tests, compatibility and the following diagnostics
are separate. New evidence uses a different storage volume after the root
filesystem reached 66 MB free; prior bundles were neither moved nor deleted.
Cross-source timings were not interleaved and cannot establish acceleration.

## Original-parent follow-up and limits

After all six main workers exit, the two first original reference/secant pairs
are diagnosed using the original immutable material parents. This separate work
performs 23,232 section / 325,248 constituent integrations and verifies 5,808
original section responses. Actual section/concrete/steel wrappers independently
count the calls; there are two model compilations, zero Newton solves and zero
accepted commits.

Each geometry retains one failing M2 section moment. Kinematic evaluation and
material-parent contributions are zero in both attribution orders. The remaining
finite-coordinate contributions are 1.234568003383174e-10 Nm (base) and
1.0486056467584604e-10 Nm (long). Kinematic evaluation is zero in every one of
5,808 field/order comparisons per geometry. These section results do not close
global member-force or support-reaction attribution.

Four serial fresh compatibility workers verify actual import paths and distinct
source revisions. Both existing binary64 strain modes reproduce 18 step files,
six complete history/checkpoint pairs and 12 cyclic element-response pairs
byte-for-byte against d81cd8e90. Compatibility costs are separately retained:
36 core entries / 92 Newton-linear counts, plus 24 direct element responses.

Broader regressions pass 706 tests in 434.49 s using the implementation loaded
before the final rounding-boundary normalization; after that correction, 77
overlapping related tests pass in 16.16 s, including 27 twofold tests. The initial
space-protection interruption after 234 passes is retained. Ruff and diff checks
pass. Implementation-head hosted general CI fails before code tests in
`Materialize exact current-source test evidence` with `legal_approval=False`.
The inspected full-test and legacy-evidence shards also stop during input
materialization at that license condition; their aggregate jobs fail accordingly.
This is not prepared full-suite or hosted acceptance.

The evidence root is `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-twofold.8GlymCUN`. Its inventory excludes `test-tmp` scratch,
which is retained in place; all included files are reopened and hash-checked.
The inventory covers 26,923 files / 1,305,731,219 bytes; every included file was
reread and hash-checked. Inventory SHA-256:
`3f9b534e6ec5132f6781e68d34ea4313020400bf218ef2b5b4be8f4b1ceaf768`.
The [machine-readable summary](rc-control-twofold-coordinates-20260909.summary.json)
links these counts and failure limits to the frozen source. Independent physics,
licensing, hardware, owner requirements and the complete roadmap remain open.
