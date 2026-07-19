# Engine v2 backend-neutral current-tangent operator

This non-promoting contract moves the actual-MGT finite-chord axial
current-tangent formula and every numeric parent from an implicit Python
callback into immutable, canonical little-endian arrays. The NumPy evaluator
is the CPU reference implementation. A HIP evaluator source, compile/host-
parser receipts, and one actual-MGT local `gfx1030` hardware-parity receipt now
exist.

## Contract

Profile:
`reference_csr_load_frame_delta_finite_chord_axial.v1`

Action in free-equation order:

`K_reference_ff*v_f + load_factor*K_frame_delta*v_global + K_finite_chord_axial_correction(u_global)*v_global`

The contract binds 12 arrays:

- reference CSR row pointer, column indices, and values;
- free-global-DOF order and prescribed-displacement background;
- frame DOFs and prepacked 12x12 load-frame stiffness deltas;
- geometry DOFs, relative-translation operators, reference chords and lengths,
  and axial stiffness.

Creation and validation fail closed on noncanonical dtype/layout, mutable byte
backing, stale descriptors or hashes, invalid CSR topology, invalid equation
maps, incompatible element shapes, and nonfinite values. Empty canonical arrays
are supported and hash as their zero-byte payload.

## Actual-MGT evidence

The G1 audit records:

- free/global DOFs: `70,560/78,282`;
- reference CSR nonzeros: `1,262,462`;
- frame/geometry elements: `5,572/5,572`;
- canonical parent bytes: `31,271,000`;
- contract hash:
  `sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177`;
- array-bundle hash:
  `sha256:19b833d0334ed923586aa9797459fec2814f138d1d7cf525d4f62ea9267a9118`.

Two actual 70,560-equation directions compare the contract evaluator with the
independent analytic callback. Infinity-norm relative differences are
`4.480068989692911e-12` and `1.8032488261425373e-16`, both within the recorded
`1e-11` normwise tolerance. The vectors are not byte-identical because the two
CPU implementations use different valid accumulation orders.

The HIP fixture derives deterministic per-free-row frame and geometry incidence
schedules from the same 12 parent arrays. The kernel applies reference CSR,
frame load-delta, and finite-chord geometry contributions in that order using
one thread per free row and one expected kernel invocation. Warning-free
`gfx1030`/`gfx1100` binaries are 56,912/57,680 bytes with hashes
`sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4`
and
`sha256:2c99d9a6e65118185b783e5151af5480e17a86cb38dac907195d67a3e421b654`.
Both binaries validate the five-equation synthetic fixture through their host-
only parser with zero HIP runtime calls.

For the actual model, the audit constructs a 21-array, 36,123,072-byte fixture
with 61,494 frame and 61,494 geometry incidences. Fixture, schedule, and
execution hashes are
`sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d`,
`sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b`,
and
`sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5`.
The audit performs an ephemeral binary write/hash/readback roundtrip and a
separate source-bound receipt recompiles the same `gfx1030`/`gfx1100` binaries.
Their hashes and byte lengths match the five-equation compile receipt exactly,
and both binaries parse the full 36,123,072-byte fixture through the host-only
path with zero HIP runtime API calls. A local Radeon RX 6900 XT `gfx1030` run
then executes the same fixture in one kernel with zero mid-action D2H transfers.
The 564,480-byte action hash is
`sha256:9c2eb32c3e568252b0b1a5c3b9e2f8176df19f597742fe6d1439b5cb733a97ab`;
it equals the device-order CPU action bitwise and has canonical CPU maximum
error `0.0625 N/m` within tolerance `13,863.865949925143 N/m`.

## Artifacts and checks

- detailed HIP transport note:
  `docs/engine-v2-hip-current-tangent-operator.md`;
- implementation:
  `src/structural_analysis/engine_v2/contracts/current_tangent_operator.py`;
- schema:
  `src/structural_analysis/schemas/current_tangent_operator_v1.schema.json`;
- HIP fixture module:
  `src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py`;
- HIP source:
  `implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp`;
- compile/host-parser receipt:
  `implementation/phase1/release_evidence/productization/engine_v2_hip_current_tangent_operator_compile_receipt.json`;
- actual-MGT host-parser receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_host_parser_receipt.json`;
- actual-MGT hardware-parity receipt and action:
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_hardware_parity_receipt.json` and
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_action.f64le`;
- focused tests:
  `tests/test_engine_v2_current_tangent_operator_v1.py`,
  `tests/test_engine_v2_hip_current_tangent_operator.py`, and
  `tests/test_engine_v2_hip_current_tangent_operator_runner.py`;
- actual-model receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_matrix_free_preconditioner_candidate_audit.json`.

```bash
python3 -m pytest -q \
  tests/test_engine_v2_current_tangent_operator_v1.py \
  tests/test_engine_v2_hip_current_tangent_operator.py \
  tests/test_engine_v2_hip_current_tangent_operator_runner.py \
  tests/test_g1_mgt_load_coupled_arc_length_adapter.py \
  tests/test_matrix_free_cpu_fgmres_state_tangent.py \
  tests/test_build_g1_mgt_matrix_free_preconditioner_candidate_audit.py
python3 scripts/run_engine_v2_hip_current_tangent_operator.py --compile-only --check
python3 scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py --check
python3 scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py --check
python3 scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py --check
```

## Claim boundary

This establishes a backend-neutral formula, equation-order, and numeric-parent
contract plus bounded CPU reference equivalence, HIP source/dual-target compile,
small and actual-scale host-parser execution, actual-input preparation, and one
local actual-MGT `gfx1030` action with CPU/HIP numerical parity. It does not
establish independent cross-device bit identity, device-resident
FGMRES/preconditioning, performance, a production nonlinear solver, an
authoritative G1 checkpoint, or G1 closure.
