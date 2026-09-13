# Isolated OpenSees 2D arithmetic diagnostic

At product source `8d87e9418a0daeec484b9820cf71c5c4675c8918`, two existing
external reaction mismatches are reproduced by an unmodified local OpenSees
build and disappear after changing one axial-extension expression in that
external build. Product arithmetic, model inputs and comparison tolerances are
unchanged. This is a controlled local diagnosis, not a replacement authoritative
runtime, independent qualification, full CI pass or release.

## Source and build isolation

The actual source is official
[OpenSees v3.7.1, fe578a5b](https://github.com/OpenSees/OpenSees/tree/fe578a5b51333e5489097f327f89d16de0797f56).
The downloaded archive SHA-256 is
`fba481b1982c415e9c9f6273c8df135bc5c2e49ad29dcdd43d482e5f97a125f0`.
All 6,164 archive files match before modification. A second archive comparison
finds exactly one changed source file:
`SRC/coordTransformation/CorotCrdTransf2d.cpp`.

Both builds use GNU 11.4, CMake Release, Python 3.10 and identical local
BLAS/LAPACK dependencies. Ubuntu dependency packages are downloaded and
extracted under the observation directory; no system packages or pinned
OpenSeesPy runtime are replaced. MPI discovery is disabled for this serial Python
target because the upstream build otherwise creates an unused OpenSeesMP target
with a missing `mumps` dependency. Tcl/Tk and Eigen include paths are explicit.
The original configuration/build failures and compiler warnings are retained.

The first compile stops at a missing Eigen include path. After that path is
specified, the unchanged source builds successfully. The original binary is
saved before editing. The subsequent incremental build compiles only the changed
transformation source and relinks; compile commands and resolved dynamic-library
hashes are identical across the two variants. Both imports report runtime 3.7.1,
but these are explicitly local builds, not the distributed 3.7.1.2 wheel.

The original full-driver payload equals the earlier pinned-runtime payload
exactly after removing timing/attempt telemetry. This ties the local baseline
to the observed failure; version text alone would not establish that connection.

## One arithmetic change

For original length `L`, local relative displacements `dx`, `dy`, and current
length `Ln`, the original expression `Ln - L` is replaced with the equivalent
identity:

```text
extension = (dx * (2 * L + dx) + dy * dy) / (Ln + L)
```

The displacement differences come directly from the local displacement vector.
This avoids subtracting two nearly equal rounded lengths. Transformation angles,
stiffness, elements, materials, loads and solver settings remain unchanged.
The original/modified source, exact patch, build commands and binaries are
retained locally with their provenance and copyright notices.

## Actual executions and unchanged comparisons

The protocol is saved before numerical execution. Each binary executes the full
driver once and the two affected planar blocks once with `NormUnbalance` tightened
from `1e-9` to `1e-12 kN`. A failed planar path stops at its first failure, with
no implicit retry. The stricter test is diagnostic only.

| Execution | External analyze calls | Outcome |
| --- | ---: | --- |
| Original, full driver | 35 | All calls return zero; two reaction metrics fail |
| Original, strict two-case diagnostic | 2 | Both return -3 at the first target; reverted outputs excluded |
| Modified, full driver | 35 | All calls return zero; both affected cases pass |
| Modified, strict two-case diagnostic | 8 | Both complete all four targets and pass |

Three fresh unchanged product analyses cover the member-feature, settlement and
portal cases, with 12 new committed load steps. The portal check is a declared
follow-up because the shared transformation also changes that third payload.
Both original and modified portal comparisons pass. All other full-driver
numerical payload blocks are exactly unchanged between the two builds.

The horizontal global force-balance errors below are checked against the known
applied horizontal loads, independently of the product's reaction values:

| Case | Original external error, N | Modified external error, N |
| --- | ---: | ---: |
| Offset/released member under uniform load | 4.96422719988357e-7 | 2.981555974335137e-16 |
| Prescribed settlement with horizontal load | 3.6312451356934616e-7 | 2.2737367544323206e-13 |

The existing product/external metric functions produce 75 comparison rows across
the accepted executions, including repeated comparisons to the same three
product results. Separate exact-rational arithmetic recounts every pass/fail
decision using the stored binary float values and unchanged tolerances. The
original two focused failures remain visible; failed strict paths have null
comparison results. All modified focused comparisons pass. These are authored
elastic benchmark cases, not 75 independent experiments or nonlinear RC learning
validation.

## Costs, preserved packet and CI boundary

The failed initial compile takes 151.677896363 s, the successful baseline compile
156.412373288 s, and the incremental modified build 1.951081524 s. The four
external child parent times are respectively 0.063766488, 0.031741134,
0.031615971 and 0.031615921 s. These single ordered observations do not establish
a speedup. Preparation/download/configuration are separate costs.

The first two product checks and source audit parent take 3.458731119 s; the
additional portal check takes 1.718828986 s. Internal replay/core/Newton work is
not separately instrumented here, so 12 committed steps are not presented as
total solver calls. The independent record audit takes 1.158239482 s; final
inventory and reread take 1.560682027 s without more numerical execution.

The completed local packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-opensees-build-ns6vb9v4`:
12,126 regular files / 638,951,334 bytes and 62 symlinks. Files and link targets
are reread; links are recorded without following them. Inventory SHA-256:
`bc7e9bf83cb1b7fa20d11b44b6fade66fad54c99efdbdf3113d69aa553585eaa`.
The [machine summary](opensees-corot2d-arithmetic-20260910.summary.json) binds
source, binaries, outcomes and the packet. The packet is sealed by workflow and
must not be appended to. It contains the original drivers, protocol, comparison
and audit scripts; no binaries or dependency archives are added to this repository.

For this exact product head,
[hosted shard 0](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34427947217/job/102717080758)
fails at `Materialize exact current-source test evidence`, citing
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Its repository test step is
skipped. The original job metadata/log is preserved in the packet. Local success
with an arithmetic-modified reference does not change that hosted outcome.

This diagnosis supports cancellation in the reference transformation as the cause
of the two observed mismatches under these conditions. The next integration work
must explicitly choose and bind an acceptable reference source/build and its
provenance, then rerun the required comparisons and same-head CI. Relabeling this
local binary as the official pinned wheel, loosening tolerances or silently
rewriting protected receipts would not resolve that work. Learned net benefit,
experimental model compatibility and the full roadmap remain open.
