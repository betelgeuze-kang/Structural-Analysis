# G1 actual-MGT matrix-free preconditioner candidate audit

This non-promoting audit compares three right preconditioners under the same
actual 70,560-equation state, Newton right-hand side, current-tangent operator
binding, and ordered host FGMRES recurrence.

## Result

The actual current tangent is now a backend-neutral immutable array contract,
not only a Python callback. It binds the reference CSR, free/global equation
order, prescribed-displacement background, 5,572 prepacked frame stiffness
deltas, and 5,572 finite-chord axial parents in 12 little-endian arrays totaling
31,271,000 bytes. The contract hash is
`sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177`.
Two actual 70,560-equation probes compare the contract evaluator with the
independent analytic callback: their infinity-norm relative differences are
`4.480068989692911e-12` and `1.8032488261425373e-16`, both below the recorded
`1e-11` normwise gate. The actions are not byte-identical because the two CPU
paths use different valid accumulation orders. This proves bounded CPU
formula/parent-array equivalence. A separate actual-MGT hardware receipt now
establishes the HIP action and CPU/HIP parity for one state and direction.

A separate HIP current-tangent source consumes the same reference CSR, sorted
frame-incidence schedule, sorted finite-chord geometry-incidence schedule,
state, and direction. Its one-thread-per-free-row kernel accumulates reference,
frame, and geometry contributions sequentially in FP64. Warning-free target
compilation produces a 56,912-byte `gfx1030` binary with hash
`sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4`
and a 57,680-byte `gfx1100` binary with hash
`sha256:2c99d9a6e65118185b783e5151af5480e17a86cb38dac907195d67a3e421b654`.
Both binaries execute the 2,600-byte, five-equation synthetic fixture parser
with zero HIP runtime calls. This is dual-target compile and small host-parser
evidence, not a device action.

The audit separately constructs the actual-MGT execution input: 70,560 free
equations, 78,282 global DOFs, 1,262,462 reference nonzeros, 5,572 frame and
5,572 geometry elements, and 61,494 incidences for each correction family. The
21-array fixture is 36,123,072 bytes with fixture, schedule, and execution
hashes
`sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d`,
`sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b`,
and
`sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5`.
It is written, read back, and hash-checked in an ephemeral directory, then
removed. A separate receipt proves that the same byte-identical `gfx1030` and
`gfx1100` binaries used by the five-equation compile receipt both parse this
full fixture through their host-only path with zero HIP runtime API calls. The
declared action then runs on a local Radeon RX 6900 XT `gfx1030` in one kernel
with zero mid-action D2H transfers. The persisted 564,480-byte `<f8` action has
hash
`sha256:9c2eb32c3e568252b0b1a5c3b9e2f8176df19f597742fe6d1439b5cb733a97ab`.
It is bitwise identical to the device-order CPU evaluator and differs from the
canonical CPU evaluator by at most `0.0625 N/m`, below the recorded
`13,863.865949925143 N/m` tolerance. This is actual-scale current-tangent
parity for one local device/state/direction, not a performance or cross-device
claim.

The fixed zero-state reference `splu(COLAMD)` diagnostic baseline converges in
3 FGMRES iterations and 6 operator actions. Its independently replayed
residual infinity norm is `4.116211867882802e-10 kN`, below the local
`5e-7 kN` gate. This remains a diagnostic baseline, not a production
preconditioner claim.

The portable-topology candidate groups the exact free global DOFs into 12,606
nodal blocks of at most 6×6 components. It builds a 408,132-entry block inverse
with zero singular-block fallbacks. Under the same recurrence:

- iteration 30 explicit residual: `0.0635380270608536 kN`;
- iteration 120 explicit residual: `0.055947460855883424 kN`;
- iteration 30-to-120 ratio: `0.8805350660683829`;
- final residual gate exceedance: `111894.92171176686×`;
- terminal state: `max_iterations`, not converged.

The apply topology is a plausible CPU/HIP primitive, but this implementation
constructs block inverses with batched `numpy.linalg.inv`, so deterministic
cross-platform construction is not claimed. More importantly, the actual-model
effectiveness gate fails even with 40 times the baseline iteration budget. This
is counterevidence against promoting nodal block Jacobi as the production
preconditioner by itself.

The ILUT frontier uses the same fixed-reference matrix with SciPy/SuperLU
`spilu`, `drop_tol=1e-6`, `fill_factor=20`, and `COLAMD`. Its L/U factors contain
12,554,899 nonzeros, or `9.944773783290112×` the reference matrix nonzeros.
After construction, the factor is copied into eight immutable little-endian
CSR/permutation arrays and applied without another SciPy call by fixed-order
forward/back substitution with ascending-column Python `fsum`. This canonical
apply converges in 6 FGMRES iterations and 8 operator actions to an independently
replayed residual infinity norm of `4.5821847600491235e-8 kN`, below the local
gate. A repeated direct factor apply is byte-identical, and its maximum
difference from the SuperLU apply is `3.979429633038656e-12 m`.

The self-describing factor manifest binds 8 files and `203136320` bytes. The
audit writes all eight full-scale little-endian arrays to an ephemeral
directory, verifies every byte length and SHA-256 digest, reloads the factor,
and binds the reloaded factor plus binary bundle hash to the matrix-free
current-tangent solver API. That bound solver performs the 6-iteration FGMRES
solve against the actual operator identity. The temporary files are then
removed and are intentionally not committed or presented as a retained release
artifact. This establishes bounded CPU diagnostic effectiveness plus a
serialized backend-neutral factor transport/apply and actual current-tangent
CPU integration contract, not production readiness. Factor construction is still
SciPy/SuperLU-specific; deterministic construction, retained plan-bound release
transport, independent cross-platform replay, HIP execution/parity, and
performance remain absent for the triangular factor apply and integrated
preconditioned Krylov path.

A separate canonical sparse-LU HIP source now consumes the same L/U CSR and
row/column permutation topology through dependency-level scheduled
forward/back substitution. With warnings treated as errors, that source
compiles byte-repeatably for both declared `gfx1030` and `gfx1100` targets:

- `gfx1030`: 57,936 bytes,
  `sha256:be3b38976dcecec4d4be06fb5a21e60158fbea7b486dc8f3d378dafe71605751`;
- `gfx1100`: 58,192 bytes,
  `sha256:9c23f463c1a124a64702d2c3b270e872c5e64f9a7e5cdf388190c104806824aa`.

Both target binaries also execute the same host-only fixture parser against the
1,232-byte canonical fixture. The parser receipt fixes zero HIP runtime API
calls and `actual_hardware=false`; this proves executable input compatibility,
not a kernel launch or numerical parity.

The same audit constructs and hash-binds the dependency schedule for the actual
70,560-equation factor and Newton right-hand side. The lower factor has 4,405
levels with maximum width 14,101; the upper factor has 4,254 levels with maximum
width 6,637. The four schedule arrays occupy 1,198,248 bytes and bind schedule
contract
`sha256:25ebdf8fdb6ab2ff8ae2801dad604a51df809353f57d3d0e144a739a284af5df`.
A complete fixture is 204,899,096 bytes. The audit materializes it in a
temporary directory, recomputes its SHA-256 by streaming file readback, requires
an exact match at
`sha256:80dc13ad269f787dd328be5ccd5018377d5d830057e75a9740e89898d401db89`,
then removes the file. It is not a retained release artifact.

This remains compile, host-parser, fixture-roundtrip, and schedule-construction
evidence. Neither target binary ran on a device in this environment. The
current one-kernel-per-level execution
would require 8,661 kernel invocations for this factor, so numerical parity,
actual factor execution, launch scalability, current-tangent HIP FGMRES
integration, and performance remain false. The blocker is therefore “not
executed,” rather than “not implemented.”

The resulting boundary is therefore narrower than “find any stronger
preconditioner”: global factor coupling is effective on this state, while the
portable local block alone is not. The next production slice must preserve that
coupling through a persisted plan-bound factor artifact and HIP apply, or
through another verified domain-decomposition/Schur/multilevel hierarchy, under
the same operator binding and explicit residual gate.

## Evidence

- detailed HIP current-tangent transport note:
  `docs/engine-v2-hip-current-tangent-operator.md`;
- receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_matrix_free_preconditioner_candidate_audit.json`;
- schema:
  `src/structural_analysis/schemas/g1_mgt_matrix_free_preconditioner_candidate_audit_v1.schema.json`;
- builder:
  `scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py`;
- canonical factor/apply contract:
  `src/structural_analysis/solvers/nonlinear/canonical_sparse_lu.py`;
- backend-neutral current-tangent contract:
  `src/structural_analysis/engine_v2/contracts/current_tangent_operator.py`;
- current-tangent manifest schema:
  `src/structural_analysis/schemas/current_tangent_operator_v1.schema.json`;
- HIP current-tangent fixture module:
  `src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py`;
- HIP current-tangent source:
  `implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp`;
- HIP current-tangent dual-target compile receipt:
  `implementation/phase1/release_evidence/productization/engine_v2_hip_current_tangent_operator_compile_receipt.json`;
- HIP current-tangent actual-MGT host-parser receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_host_parser_receipt.json`;
- HIP current-tangent actual-MGT hardware receipt and action:
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_hardware_parity_receipt.json` and
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_action.f64le`;
- HIP triangular apply source:
  `implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp`;
- HIP triangular dual-target compile receipt:
  `implementation/phase1/release_evidence/productization/engine_v2_hip_sparse_lu_apply_compile_receipt.json`.

```bash
python3 scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py --check
python3 scripts/run_engine_v2_hip_current_tangent_operator.py --compile-only --check
python3 scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py --check
python3 scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py --check
python3 scripts/run_engine_v2_hip_sparse_lu_apply.py --compile-only --check
python3 -m pytest -q \
  tests/test_engine_v2_canonical_contract.py \
  tests/test_engine_v2_current_tangent_operator_v1.py \
  tests/test_engine_v2_hip_current_tangent_operator.py \
  tests/test_engine_v2_hip_current_tangent_operator_runner.py \
  tests/test_canonical_sparse_lu_factor.py \
  tests/test_matrix_free_cpu_fgmres_state_tangent.py \
  tests/test_engine_v2_hip_sparse_lu_apply.py \
  tests/test_engine_v2_hip_sparse_lu_apply_runner.py \
  tests/test_build_g1_mgt_matrix_free_preconditioner_candidate_audit.py
```

## Claim boundary

The receipt records bounded CPU counterevidence for nodal block Jacobi and
bounded CPU diagnostic effectiveness for host ILUT. The canonical factor
contract, full-scale ephemeral binary roundtrip, and ordered CPU triangular
apply are implemented, tested, and bound to the actual current-tangent solver
API. The current tangent itself is separately hash-bound as 12 immutable parent
arrays and replayed through a NumPy FP64 reference evaluator against two
independent actual-MGT directions. A HIP source and dual-target binaries parse
both the small fixture and the actual 36,123,072-byte current-tangent fixture
through the host-only path. The current-tangent action additionally executes on
one local `gfx1030` and passes canonical-tolerance plus device-order-bitwise
parity. The actual-factor HIP dependency schedule is not executed on a device.
It does not claim deterministic block-inverse or ILUT construction, a
retained plan-bound release artifact, independent cross-platform factor replay,
production preconditioner effectiveness, HIP triangular apply parity,
device-resident current-tangent FGMRES/preconditioning, independent `gfx1100`
parity, performance,
production matrix-free Krylov, an authoritative G1 checkpoint, or G1 closure.
