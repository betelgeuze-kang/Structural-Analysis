# G1 Component Operator Reconciliation Audit (F2c, non-promoting)

Step F2c of the D→E→F plan. F2b-ii-a found the assembled free-space tangent is
decorrelated from the physical residual directional derivative
(`cosine(K.v, J_phys.v) ≈ 0.02`). This audit decomposes `J_phys.v` component by
component and ranks which component drives the decorrelation, so a later slice can
adjust only the offending component.

It is an audit only: it does not modify the solver, does not promote G1, does not
regenerate the 0.656 continuation checkpoint, and writes only an untracked
`*.local.json`.

- Helpers: `implementation/phase1/g1_operator_component_audit.py`
- Driver: `implementation/phase1/run_g1_component_operator_reconciliation_audit.py`
- Tests: `tests/test_g1_component_operator_reconciliation_audit.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_component_operator_reconciliation_audit.local.json`

## Method

For a random free-space direction `v`:
- `J_phys.v` = matrix-free physical residual directional derivative;
- `K_total.v` = assembled free-space tangent action;
- per-component `J_c.v` = directional derivative of each physical internal-force
  component (frame / spring / shell_membrane / shell_bending_drilling /
  material_stress_correction), via `include_component_forces`;
- per-component norm, cosine with `J_phys.v`, contribution ratio; mismatch
  classified as `consistent` / `scale_factor` / `decorrelated_not_scale_factor`;
- spring tangent (`K_spring.v`) cross-checked against the spring residual JVP
  (spring internal force is linear `K_spring @ u`, so they must agree).

## Observed on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state:

- global `cosine(K_total.v, J_phys.v) ≈ 0.020`, `||J_phys.v|| ≈ 3.48e12`,
  `||K_total.v|| ≈ 6.46e10` (decorrelated, ~54x magnitude gap);
- component reconstruction is exact (`sum(J_c.v)` vs `J_phys.v`: cosine 1.0,
  rel error ~7e-17);
- **frame** carries 99.98% of `||J_phys.v||` (norm ~3.48e12) and is aligned with
  `J_phys.v` (cosine 0.9998);
- shell_membrane ~1.8% (cosine ~0.02), shell_bending_drilling ~0.6%; spring and
  material_stress_correction non-contributing at this state.

### Ranked suspect: `frame` (priority 1)

The physical residual's directional derivative is essentially the **frame**
component (reference-geometry linear force recovery, `quasi_tangent_k_eq_at_u`
model), which the assembled tangent fails to reproduce in both magnitude (~54x)
and direction (cosine 0.02). Springs (linear `K_spring @ u`) and shell are not the
drivers.

## Next slice (per F2c case taxonomy: Case 2/3 — frame)

Reconcile the reference-geometry frame internal-force linearization with the
assembled frame tangent: reference linear frame force vs geometric/material
tangent, geometric (P-Delta) stiffness sign and load scaling, service-material vs
physical material tangent, and any unit/scale conversion in the frame fastpath.
The current fastpath is not a full corotational beam and must not be described as
one.

## State-updated axial follow-up

A conservative finite-chord axial replacement now has an exact energy gradient
and consistent tangent-action kernel. It replaces only the reference linear axial
term; bending/torsion remain reference-geometry small-rotation terms, so the
full-corotational claim remains false.

The actual uncoarsened MGT preflight preserves two distinct results. With only
the raw `*MATERIAL` table, all 5,572 selected frame sections resolve but only
5,493 frame materials resolve; the remaining 79 reference IDs 16 and 26–31, so
the strict raw-table prepack fails closed with no fallback. Separately, every one
of the 29 `*DGN-MATL` rows has one exact normalized `(TYPE, MNAME)` match to a
source `*MATERIAL` row. Copying only that matched row's existing analysis
properties creates 24 distinct-ID aliases and gives 5,572/5,572 diagnostic
coverage. No DGN numeric design field, fuzzy name match, or database inference is
consumed. The resolved prepack succeeds, but the identity inheritance remains
engineer-review-required, so readiness stays `partial` and evidence closure stays
false. See `g1_mgt_state_updated_frame_axial_geometry_preflight.json`.

The separate actual-adapter receipt then enables those review-dependent aliases
and connects the prepacked finite-chord axial correction to both the physical
residual and an analytic consistent state-tangent callback. All 5,572 frame
elements use resolved source-derived properties with fallback count zero. For
this path, the solve residual is evaluated from the same reference CSR,
load-frame delta, and finite-chord correction parents used by the analytic
tangent; the component-force sum remains a diagnostic cross-check. At the
full-unit predictor, the parent residual is byte-repeatable at
`3823.8140951064206 N`; the component-sum residual is
`3823.8140951476234 N`, and the maximum vector difference is
`1.922977389767766e-6 N`, below the scale-relative audit tolerance
`0.0001794582387319392 N`. The canonical residual formula hash is
`sha256:2da9d3377eaf3cd9b196e82535c3a3593502079652306bc5705e13d910cca62f`
and is independently recomputed by the receipt builders. After subtracting the
linear solve floor, the observed
remainder order is `1.9999997268745022`, classified as measurable quadratic.
The analytic action agrees with an independently evaluated centered-residual
action within relative error `6.223759573646822e-8`. At load factor `1.0`, the
same normalized probe direction gives a
zero-versus-predictor tangent-action difference of
`2935.9022702476345 kN/m`, so the adapter correctly disables its state-invariant
CSR claim and requires current-state action evaluation. This is connection and
diagnostic evidence only: the DGN identity inheritance still needs engineer
review, and full corotational bending/torsion, nonlinear continuation,
production Krylov/HIP parity, an accepted nonlinear load-`1.0` checkpoint, and
G1 closure remain false. See
`g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.json`.

A bounded matrix-free CPU FGMRES smoke then factors the zero-state reference CSR
only as a fixed right preconditioner and solves one current-tangent Newton
correction at the full-unit predictor. It converges in 3 iterations and 5 current
operator actions; the independently replayed linear residual is
`4.116211867882802e-10 kN`. Applying the uncommitted full correction reduces the
physical residual from `3823.8140951064206 N` to
`0.002323337105281098 N`. The recurrence fixes dot/norm, projected solve, and
basis-update reductions to the Engine v2 ordered Python-`fsum` profile and binds
the actual free-equation order, residual formula, reference load, tangent action,
and preconditioner hashes. The tangent formula and 12 canonical parent arrays
are contract-bound; the NumPy evaluation order and SuperLU output remain outside
the cross-platform recurrence claim. This establishes one diagnostic
current-tangent solve,
not continuation, end-to-end cross-platform determinism, preconditioner
scalability, HIP parity, or an accepted checkpoint. See
`g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.json`.

A separate two-attempt matrix-free Newton diagnostic retains both descending
full-step trials in memory.
Across the two analytic current-tangent solves it uses 5 FGMRES iterations and 10
operator actions; the maximum independently replayed tangent residual is
`4.116211867882802e-10 kN`. The first attempt reduces the physical residual from
`3823.8140951064206 N` to `0.002323337105281098 N`; the second reduces it to
`1.1767242540372536e-6 N`. Both are accepted only as in-memory diagnostic states,
and the latter passes the local `0.0005 N` gate by a factor of about 425. The
earlier apparent `0.05 N` floor was traced to cancellation-prone chord-length and
axial-force subtraction and is removed by algebraically equivalent stable
extension, correction, and tangent formulas. No load-controlled continuation,
persisted load-`1.0` checkpoint, production recurrence/HIP parity, or G1 closure
is claimed. See
`g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.json` and
`docs/g1-mgt-state-updated-matrix-free-newton-diagnostic.md`.

A load-controlled diagnostic then starts from the exact zero accepted state and
advances the same actual 70,560-equation finite-chord axial problem through
semantic `LIVE` factors `0.25`, `0.5`, `0.75`, and `1.0`. All four steps are
accepted with one analytic current-tangent FGMRES solve and full line-search alpha
per step. Every solve uses at most 3 iterations, and the maximum independently
replayed tangent residual is `1.7851387609877506e-10 kN`. Every accepted step
passes the local `0.0005 N` residual gate and the absolute-or-relative increment
gate; the maximum accepted relative increment is `4.5583426984171883e-5` against
`1e-4`. The final physical residual is `0.0004447424730642524 N`. Restarting from
the accepted `0.5` checkpoint reproduces the terminal state and binary64
displacement vector exactly; the final vector has 70,560 values, 564,480 bytes,
and SHA-256
`c8683e1b58b3a81be967835cb0d549b14ac410cf848288f4bcb2233a1a91fb4d`.

Across the fixed, restart, direct, rollback, adaptive, and local-quadratic
probes, all 20 tangent receipts use one operator-binding hash and one fixed
reference-preconditioner pattern/value identity. All 20 use the ordered host
arithmetic profile. This is an auditable CPU recurrence bridge, not an
end-to-end cross-platform callback/SuperLU guarantee or HIP parity.

A separate direct `0 -> 1.0` probe passes the same local gate after two Newton
corrections with residual `1.1767242540372536e-6 N`. Around that converged state,
one-direction perturbations of `4e-6`, `2e-6`, and `1e-6 m` followed by one full
analytic-current-tangent correction leave residuals `0.009016784547384304`,
`0.0022542193351000606`, and `0.0005635606662508508 N`. The observed-order range
is `1.9999850689943242` to `1.9999851530959427`, while the normalized quadratic
coefficient spread is `2.0640261161548417e-5`; this passes only a local
directional quadratic-convergence gate. A one-correction-limited
actual-model probe stops at `0.002323337105281098 N` and restores the zero
accepted checkpoint exactly, separating convergence evidence from rollback
control-flow evidence. The same actual problem also runs an adaptive controller
with one Newton correction allowed per attempted step. Its attempt targets are
`1.0, 0.5, 1.0, 0.75, 1.0`: the two direct large-step attempts fail at
`0.002323337105281098 N` and `0.0013068756297798244 N`, roll back exactly, and
halve the step. The accepted `0.5, 0.75, 1.0` checkpoints reach a final residual
of `0.0004446982484296314 N`; restart from the accepted `0.5` checkpoint
reproduces the adaptive terminal vector and hashes exactly. This closes only the
local finite-chord axial adaptive-control diagnostic
path. DGN identity inheritance remains under engineer review. Full-corotational
bending/torsion, full frame/shell/material consistency, material-state
commit/rollback, arc-length, production/deterministic Krylov and preconditioner
evidence beyond the bounded ordered-host recurrence, HIP parity, an authoritative
G1 checkpoint, and G1 closure remain
false. See
`g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.json`.

## Linear-reference continuation follow-up

The corrected actual-MGT semantic `LIVE` adapter now also runs from the explicit
zero accepted state through load factors `0.25`, `0.75`, and `1.0` with its exact
state-invariant linear reference-geometry CSR Jacobian. The final residual is
`1.8550488967150613e-06 N`; regularization and fallback counts are zero. A
serialized `0.75` checkpoint restarts to a byte-identical full-load vector, and a
separate one-iteration failure probe performs exact rollback.

This is control-flow and persistence evidence for the linear adapter only. The
raw table still has 79 unresolved bindings; exact source-derived aliases remove
the diagnostic prepack gap but remain engineer-review-dependent and are not used
by this linear receipt. A separate actual-adapter receipt connects the
finite-chord axial current-state action, but a complete frame/shell nonlinear
current tangent, quadratic convergence, material-state commit/rollback, full
arc-length continuation, production HIP, and G1 checkpoint/closure claims remain
false. See
`g1_mgt_semantic_live_linear_newton_continuation_receipt.json` and
`docs/g1-mgt-semantic-live-linear-newton-continuation.md`.

## Not done here

No production nonlinear solver closure, no accepted nonlinear G1 checkpoint, and
no G1 promotion.
