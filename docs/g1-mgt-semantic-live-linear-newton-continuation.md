# G1 actual-MGT semantic LIVE linear-reference Newton continuation

This non-promoting diagnostic starts the corrected actual-MGT adapter from the
explicit accepted state `u=0, lambda=0` and exercises adaptive load-controlled
Newton, line search, accepted-state checkpoints, failed-step rollback, binary
checkpoint serialization, and restart replay.

The bound residual is currently linear and reference-geometry based. Its
1,264,133-nnz CSR Jacobian is exact for that narrow residual, but it is not a
state-updated geometric/material tangent. This receipt therefore does not satisfy
the G1 full-load checkpoint contract even though the diagnostic reaches
`lambda=1.0`.

## Actual-model result

- actual uncoarsened MGT: 13,047 nodes, 78,282 global DOFs, 70,560 free
  equations;
- authored `LIVE` load: 6 nodal rows and 3,644 uniform global-Z plate-pressure
  rows, resultant `-50,628,330.359766744 N` in Z;
- accepted load factors: `0.0 -> 0.25 -> 0.75 -> 1.0`;
- accepted/failed direct steps: `3/0`, with full line-search alpha `1.0`;
- final residual: `1.8550488967150613e-06 N`;
- maximum explicit tangent-solve residual: `4.2724750528577715e-06 N`;
- maximum centered tangent-action error: `9.06263396416307e-06 kN`;
- regularization/fallback/material-state commits: `0/0/0`.

The serialized `lambda=0.75` restart vector contains 70,560 little-endian
binary64 values and has hash
`sha256:54ff7e76815eea773df1ecb2e7eb70f4d7045c35449f3a618af6fa0d431ca2f8`.
Reloading it validates the checkpoint state hash and reproduces the full-load
vector byte-for-byte. The final vector hash is
`sha256:e598d1b996deb2260eac80c7c66b4da7e64202513c011f570f7c7dcc659279b2`;
the direct and restarted final state hash is
`sha256:af0c565b0fd9c796b7f2fd4f39eeae676f0665266ad60ed3f24257899d7e1b4c`.

A separate actual-model probe limits Newton to one iteration. Its trial
correction is rejected, the accepted zero state remains byte-exact, and the load
increment reduction terminates at the configured minimum. This proves rollback
control flow for the linear diagnostic only; no nonlinear material state exists
to commit or restore.

## Evidence and verification

- receipt and summary:
  `implementation/phase1/release_evidence/productization/g1_mgt_semantic_live_linear_newton_continuation_{receipt,summary}.json`;
- restart and full-load vectors:
  `implementation/phase1/release_evidence/productization/g1_mgt_semantic_live_linear_newton_{restart_0p75,full_load}_free_displacement.f64le`;
- schema:
  `src/structural_analysis/schemas/g1_mgt_semantic_live_linear_newton_continuation_v1.schema.json`;
- builder:
  `scripts/build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py`.

```bash
python3 scripts/build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py --check
python3 -m pytest -q \
  tests/test_g1_mgt_semantic_live_linear_newton_continuation.py \
  tests/test_build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py
```

## Claim boundary

The diagnostic consumes the actual semantic `LIVE` load and proves deterministic
linear-reference Newton/restart/rollback mechanics. The raw `*MATERIAL` table
still binds only 5,493 of 5,572 frame elements. A separate fail-closed preflight
shows that all 29 `*DGN-MATL` rows have one exact normalized type/name match to a
source `*MATERIAL` row and that 24 distinct-ID aliases raise diagnostic property
coverage to 5,572/5,572 without consuming DGN numeric design fields or fuzzy
inference. Those aliases are not applied in this linear-reference receipt and
remain engineer-review-required. A separate actual-adapter receipt applies them
and detects a finite-chord axial state-dependent tangent and measurable quadratic
remainder. A separate bounded matrix-free Newton receipt uses that analytic
current-state tangent at `lambda=1.0`, accepts two descending full corrections,
and reaches an in-memory residual of `1.1767242540372536e-6 N`. A separate
load-controlled finite-chord axial receipt reaches `lambda=1.0` with local
`0.0005 N` residual-plus-increment acceptance, exact midpoint restart, and an
iteration-limited rollback probe. Its adaptive replay also exercises actual
failed-step reduction and exact midpoint restart. Neither receipt is an authoritative G1
checkpoint. This linear diagnostic also does not
prove a complete frame/shell nonlinear current tangent, quadratic convergence,
material commit/rollback, arc-length continuation, production Krylov/HIP
execution, a loadable
`mgt-direct-residual-newton-state.v1` checkpoint, or G1 closure.
