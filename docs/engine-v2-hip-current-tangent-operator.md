# Engine v2 HIP current-tangent operator

This optional backend adapter transports the backend-neutral current-tangent
contract into a canonical HIP fixture. It is deliberately split into three
evidence levels: source/target compilation, host-only fixture parsing, and
actual device execution. Only the first two are present in the committed
compile receipt, and its parser coverage is limited to the five-equation
synthetic fixture. Separate committed receipts cover full actual-MGT host
parsing and one local `gfx1030` hardware action.

## Execution contract

The fixture contains the 12 immutable parent arrays from
`reference_csr_load_frame_delta_finite_chord_axial.v1`, one free state, one
free direction, a load factor, a global-to-free map, and deterministic frame
and geometry incidence schedules. Incidences are sorted by element and local
DOF within each free row.

The device execution profiles are:

- schedule: `free_row_sorted_element_local_incidence.v1`;
- execution: `one_thread_per_free_row_reference_frame_geometry.v1`;
- accumulation:
  `reference_then_sorted_frame_then_sorted_geometry_sequential_fp64.v1`.

One thread owns each free row, so the reference CSR, frame load-delta, and
finite-chord geometry contributions are accumulated without atomics. The
declared fixture needs one kernel invocation. `-ffp-contract=off` fixes the
compile-side contraction policy. The actual-MGT hardware receipt supplies the
separate numerical-parity evidence for one state and direction.

## Compile and parser evidence

The source compiles with `-Werror -ffp-contract=off -std=c++17` for both
declared targets:

- `gfx1030`: 56,912 bytes,
  `sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4`;
- `gfx1100`: 57,680 bytes,
  `sha256:2c99d9a6e65118185b783e5151af5480e17a86cb38dac907195d67a3e421b654`.

Each binary executes the host-only parser against the same 2,600-byte,
five-equation fixture. The parser validates the binary dimensions, topology,
schedule hashes, and payload length while reporting zero HIP runtime calls and
`actual_hardware_execution=false`. These observations prove target compilation
and executable input compatibility only; they are not kernel or parity
evidence.

## Actual-MGT input preparation

The G1 audit separately constructs the full input for the normalized current
Newton right-hand-side direction:

- free/global DOFs: `70,560/78,282`;
- reference nonzeros: `1,262,462`;
- frame/geometry elements: `5,572/5,572`;
- frame/geometry incidences: `61,494/61,494`;
- canonical arrays: `21`;
- fixture size: `36,123,072` bytes;
- fixture hash:
  `sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d`;
- schedule hash:
  `sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b`;
- execution hash:
  `sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5`.

The audit materializes this payload only in a temporary directory, verifies an
exact SHA-256 file readback, and removes it when the temporary context exits.
A separate source-bound receipt recompiles both declared targets and runs each
binary's host-only parser against the full payload. The binaries match the
five-equation compile receipt byte-for-byte; both actual-scale validations bind
fixture hash `sha256:e116…0115d`, report zero HIP runtime API calls, and pass.
The hardware receipt then executes this exact fixture on an AMD Radeon RX 6900
XT (`gfx1030`). The device reports one kernel invocation, zero mid-action D2H
transfers, and one final blocking D2H synchronization. Its 70,560-value action
is retained as a 564,480-byte canonical `<f8` artifact with hash
`sha256:9c2eb32c3e568252b0b1a5c3b9e2f8176df19f597742fe6d1439b5cb733a97ab`.
The action is bitwise identical to the device-order CPU evaluator. Its maximum
difference from the canonical CPU evaluator is `0.0625 N/m`, below the
scale-derived `13,863.865949925143 N/m` tolerance; the relative maximum error
is `4.508122065356342e-17`.

This proves one actual-MGT current-tangent device action and numerical parity,
not device-resident FGMRES/preconditioning, an independent `gfx1100` run, or a
performance sweep.

## Artifacts and verification

- backend adapter:
  `src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py`;
- HIP source:
  `implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp`;
- runner:
  `scripts/run_engine_v2_hip_current_tangent_operator.py`;
- compile receipt:
  `implementation/phase1/release_evidence/productization/engine_v2_hip_current_tangent_operator_compile_receipt.json`;
- actual-MGT host-parser builder and receipt:
  `scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py` and
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_host_parser_receipt.json`;
- actual-MGT hardware runner, receipt, and action:
  `scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py`,
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_hardware_parity_receipt.json`, and
  `implementation/phase1/release_evidence/productization/g1_mgt_hip_current_tangent_action.f64le`;
- actual-input receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_matrix_free_preconditioner_candidate_audit.json`.

```bash
PYTHONPATH=src:implementation/phase1:scripts python3 \
  scripts/run_engine_v2_hip_current_tangent_operator.py \
  --compile-only --check
PYTHONPATH=src:implementation/phase1:scripts python3 -m pytest -q \
  tests/test_engine_v2_hip_current_tangent_operator.py \
  tests/test_engine_v2_hip_current_tangent_operator_runner.py
PYTHONPATH=src:implementation/phase1:scripts python3 \
  scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py \
  --check
PYTHONPATH=src:implementation/phase1:scripts python3 \
  scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py \
  --check
PYTHONPATH=src:implementation/phase1:scripts python3 \
  scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py \
  --check
```

## Claim boundary

This slice establishes a canonical HIP transport format, deterministic
free-row schedules, dual-target warning-free compilation, small and actual-MGT
host-parser execution, and full actual-MGT input construction with ephemeral
hash roundtrip. One local `gfx1030` device action establishes actual-MGT
current-tangent CPU/HIP numerical parity for one state and direction. It does
not establish independent `gfx1100` parity, device-resident
FGMRES/preconditioning, performance, production nonlinear readiness, or G1
closure.
