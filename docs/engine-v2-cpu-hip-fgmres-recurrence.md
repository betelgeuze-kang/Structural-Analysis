# Engine v2 CPU/HIP FGMRES recurrence parity

This slice extends the primitive parity fixture with a narrow HIP FGMRES
recurrence probe. The optional HIP adapter remains outside the backend-neutral
`structural_analysis.engine_v2` package. The canonical little-endian fixture is
bound to the same ExecutionPlan, EquationScaling, reduced-CSR identity, and
operator-values hashes as the deterministic CPU run.

## Reference and checkpoint contract

The fixture contains 66 free equations and 4,356 reduced-CSR entries. It defines
three logical executions:

- `converged_full_cycle`: converges in 21 iterations and 43 matvecs;
- `restart_max_iterations`: uses restart length one, records `restarted` and
  `max_iterations` dispositions, and terminates after two iterations and five
  matvecs;
- `checkpoint_resume`: loads the forced-restart case's canonical checkpoint at
  iteration one, matvec three, and next restart index one, then executes only
  the remaining suffix to the same iteration-two/matvec-five terminal state.

The checkpoint uses `structural-analysis-cpu-fgmres-checkpoint.v1`: a canonical
little-endian 48-byte header followed by exact FP64 solution and scaled
recurrence-residual vectors. Its manifest binds the ExecutionPlan, scaling,
reduced CSR and operator, original inputs and solver parameters,
observation/restart prefix, global counters, convergence threshold, vector
hashes, recurrence-contract hash, and checkpoint hash. CPU loading and resume
fail closed on byte, source, or manifest tampering and reproduce the exact
one-shot run manifest and run hash.

## Current multi-block execution

The current HIP source enqueues a fixed, same-stream sequence of device-guarded
kernels. It uses 64 threads per block and four blocks per case for operator and
partial-reduction stages. Block-local fixed binary-tree FP64 reductions feed a
final reduction kernel. Current, residual, work, Arnoldi basis, and
preconditioned basis vectors use a dimension-derived device-global Krylov
workspace.

The recurrence uses
`operator_derived_left_scaled_jacobi_right.v1`. The inverse diagonal is derived
from the exact positive diagonal of `D_free^-1 A_free` through the authoritative
reduced-CSR value mapping. CPU construction/replay, checkpoint loading, the HIP
fixture validator, and the HIP executable all recompute and verify the same
bytes. The 66-equation fixture binds preconditioner contract hash
`sha256:4307b187a323895a1a772c217e7f6889f497bb06060415b89e6b1d5f35ceb84e`.

The actual RX 6900 XT (`gfx1030`) runtime receipt binds the exact 3,710-kernel
sequence, four operator blocks per case, zero mid-recurrence host transfers, one
blocking final D2H synchronization, one checkpoint H2D transfer, and zero
completed-iteration replay. The device reports cooperative-grid launch support
as unavailable, so this probe uses an explicitly ordered multi-kernel route.

Terminal and restart-disposition histories match the deterministic CPU
reference exactly. The maximum solution absolute error is
`1.7763568394002505e-15`, and the maximum residual-observation absolute error is
`5.921189442609352e-16`, below the declared absolute and relative tolerance
`1e-11`. The checkpoint-resumed suffix has zero final-solution error and
`5.551115123125783e-17` maximum observation error. The
receipt binds:

- checkpoint:
  `sha256:1e0bcf0a0be8f3c97455df9de5dba597715c9ece8f60425213b13a231f896e51`;
- artifact data:
  `sha256:36be341af84e4f4836e72aae90a04177671bc0396dcf302b1fd6d1ea9d286068`;
- recurrence contract:
  `sha256:21636afa7d56302994375d847f776075fb1caffd56054560484876bf8e8867e5`;
- HIP binary:
  `sha256:de3133fd1877977a65e362fa577835893857ed755c89ac9a1bbab4eba1aa2441`.

The source-bound runtime receipt validates against the current source, schema,
and focused tests. It was generated from a dirty development worktree, so it
sets `exact_source_commit_claim=false` and cannot establish a clean source
commit or wheel identity. A second actual execution produced an exactly equal
runtime-output and CPU-comparison object. This local repetition is not an
independent-device or signed clean-source receipt.

## Compile-only evidence

`engine_v2_hip_fgmres_multiblock_compile_receipt.json` separately records an
offline `gfx1030` target compile of the same binary hash. Its schema fixes
`contract_scope=target_compile_only` and forces hardware execution, numerical
parity, checkpoint-resume parity, production recurrence, and performance claims
to `false`. It is useful where a GPU device is not exposed, but it never
substitutes for the actual runtime receipt.

## Actual-MGT current-tangent CPU bridge

The actual 70,560-free-equation finite-chord axial diagnostic now reuses the
CPU recurrence's `ascending_index_python_fsum_fp64.v1` accumulation order for
dot products, norms, projected back-substitution, and basis updates. Its
matrix-free solver binds and rechecks the actual free-equation order, residual
formula, reference load, analytic current-tangent action contract, and fixed
reference-preconditioner pattern/value hashes. The full fixed-step, restart,
direct, rollback, adaptive, and local-quadratic evidence contains 20/20 bound
tangent solves with one operator-binding hash and one preconditioner identity.

This narrows the production current-tangent recurrence gap but does not close
it. The operator formula and 12 canonical parent arrays are now contract-bound,
but the NumPy evaluator's reduction order and SciPy SuperLU output are not part
of the cross-platform ordered-recurrence claim. No Engine v2
EquationScaling/ExecutionPlan has yet been bound to the actual MGT adapter, and
the nonlinear action has not run inside the HIP FGMRES recurrence. A separate
one-action receipt now covers the actual-MGT current-tangent kernel only.
Consequently,
end-to-end cross-platform
determinism, production preconditioner effectiveness, integrated CPU/HIP
nonlinear-solve parity, and G1 closure remain false.

A bounded preconditioner audit also tests the existing free-global-node 6×6
block-Jacobi topology under the same actual operator binding and host
recurrence. The 12,606-block/408,132-entry candidate has zero singular-block
fallbacks, but its explicit residual is still `0.055947460855883424 kN` after
120 iterations, or `111894.92171176686` times the local gate. Its current block
construction also uses batched `numpy.linalg.inv`, so deterministic construction
is false. The topology may remain useful as one primitive in a stronger
hierarchy, but this result is counterevidence against using it alone as the
production CPU/HIP preconditioner.

The same audit now bounds the opposite side of the effectiveness frontier with
a host SciPy/SuperLU ILUT factor. At `drop_tol=1e-6`, `fill_factor=20`, and
`COLAMD`, its 12,554,899 L/U nonzeros are `9.944773783290112` times the reference
matrix nonzeros. The factor is copied into eight immutable little-endian
CSR/permutation arrays, then applied without SciPy through inverse row
permutation, ordered CSR forward/back substitution, and forward column
permutation. The within-row accumulation is ascending-column Python `fsum`.
This path reaches `4.5821847600491235e-8 kN` in 6 iterations and 8 operator
actions; its direct apply is byte-repeatable and differs from SuperLU by at most
`3.979429633038656e-12 m`. The canonical manifest binds eight files and
`203136320` bytes. The actual-scale audit writes, hashes, reloads, and validates
all eight arrays in an ephemeral directory, then binds the reloaded factor and
bundle hash to the matrix-free current-tangent solver API. That bound CPU
solver reaches the same 6-iteration result under the actual operator identity.
This does not promote production readiness: construction remains
SciPy/SuperLU-specific, no factor bytes are retained as a plan-bound release
artifact, and no independent cross-platform/HIP triangular replay or
performance evidence exists.

The actual 70,560-equation current tangent is also captured as a separate
backend-neutral contract. Twelve immutable little-endian parent arrays totaling
31,271,000 bytes bind the reference CSR, equation order, prescribed background,
frame load delta, and finite-chord axial correction under contract hash
`sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177`.
Two independent actual-MGT directions replay through both the contract NumPy
evaluator and the original analytic callback with infinity-norm relative
differences `4.480068989692911e-12` and `1.8032488261425373e-16`. This moves the
operator formula and its numeric parents into a transportable CPU reference
contract. A separate HIP evaluator source now compiles for both declared
targets and both binaries execute a five-equation host-only fixture parser with
zero HIP runtime calls. The actual 70,560-equation input is also serialized as
a 36,123,072-byte ephemeral fixture with 61,494 sorted frame and geometry
incidences apiece. Its fixture, schedule, and execution hashes are
`sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d`,
`sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b`,
and
`sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5`.
The same byte-identical target binaries now also parse the full actual fixture
through the host-only path with zero HIP runtime calls. A local Radeon RX 6900
XT `gfx1030` run additionally executes that fixture in one kernel with no
mid-action D2H transfer. Its 70,560-value action is bitwise equal to the
device-order CPU reference and has canonical CPU maximum error `0.0625 N/m`
within the recorded tolerance. This establishes one actual-scale operator
action, not device-resident FGMRES/preconditioning or performance.
See `docs/engine-v2-current-tangent-operator.md` and
`docs/engine-v2-hip-current-tangent-operator.md`.

The canonical triangular topology now also has a separate HIP implementation
and fail-closed receipt contract. It validates row/column permutations plus
dependency-level schedules, then performs one same-stream RHS permutation,
six lower levels, six upper levels, and one solution permutation for a
nontrivial eight-equation fixture. Warning-free `-Werror` target compilation is
byte-repeatable for `gfx1030` (57,936 bytes,
`sha256:be3b38976dcecec4d4be06fb5a21e60158fbea7b486dc8f3d378dafe71605751`)
and `gfx1100` (58,192 bytes,
`sha256:9c23f463c1a124a64702d2c3b270e872c5e64f9a7e5cdf388190c104806824aa`).
Both binaries execute the same host-only fixture parser with zero HIP runtime
calls. The committed sparse-LU evidence does not execute either binary on a
device, so no numerical parity, actual 70,560-factor apply, production-size
schedule execution, current-tangent HIP FGMRES recurrence, or performance
claim is promoted.
The actual audit does construct the full-factor
dependency schedule: 4,405 lower plus 4,254 upper levels, 1,198,248 schedule
bytes, schedule contract
`sha256:25ebdf8fdb6ab2ff8ae2801dad604a51df809353f57d3d0e144a739a284af5df`,
and 8,661 expected launches under the current one-kernel-per-level design. It
also performs an ephemeral 204,899,096-byte combined-fixture write and streaming
hash readback. This is preparation and input-contract evidence, not device
execution or scalability.
See `docs/engine-v2-hip-sparse-lu-apply.md`.

## Stage 4 cross-device intake

The architecture-neutral
`engine-v2-hip-fgmres-device-receipt.v1` contract accepts either `gfx1030` or
`gfx1100`. It binds the exact source-set checksum, commit, wheel hash, fixture
and preconditioner identities, compiler and binary, raw runtime output, and the
recomputed CPU/HIP comparison. Operator organization, runner, execution
location, and the `gfx1100` independence attestation are part of the signed
payload. Detached Ed25519 signatures are verified from the embedded public key;
the tool never reads or stores a private key.

`engine_v2_hip_fgmres_stage4_status.json` is the fail-closed pair gate. The
current status is `partial`. A new direct local `gfx1030` device receipt binds
the actual RX 6900 XT execution to wheel
`sha256:85f64c517f09c95195b6afa0bac6a73f0b231d6cddfdab46ef577ee8a074e98e`
and receipt
`sha256:b16712d1adfbc763246da773b77eff22a2d0d1592cc71940a4ff5a921e2637cf`.
Its numerical and checkpoint parity claims pass, but it was produced from a
dirty worktree and remains unsigned. The legacy local receipt is also valid
actual-hardware evidence but is not wheel-bound. No independent `gfx1100`
device receipt is attached.
Stage 4 becomes `ready` only when direct device-runner receipts for both
architectures have clean exact source claims, the same commit/source set,
wheel and fixture, verified numerical/checkpoint parity, different
organizations/runners/signers/public keys, and an external independence
attestation. Even that result leaves production recurrence and performance
claims false.

Artifacts:

- `implementation/phase1/release_evidence/productization/engine_v2_cpu_hip_fgmres_recurrence_receipt.json`
- `implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_multiblock_compile_receipt.json`
- `implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_gfx1030_device_receipt.json`
- `implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_stage4_status.json`
- `src/structural_analysis/schemas/cpu_hip_fgmres_recurrence_parity_v1.schema.json`
- `src/structural_analysis/schemas/hip_fgmres_multiblock_compile_receipt_v1.schema.json`
- `src/structural_analysis/schemas/hip_fgmres_device_receipt_v1.schema.json`
- `src/structural_analysis/schemas/hip_fgmres_stage4_status_v1.schema.json`
- `scripts/run_engine_v2_hip_fgmres_device_receipt.py`
- `scripts/build_engine_v2_hip_fgmres_stage4_status.py`
- `implementation/phase1/hip_kernels/engine_v2_fgmres_recurrence.hip.cpp`
- `implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp`
- `implementation/phase1/release_evidence/productization/engine_v2_hip_sparse_lu_apply_compile_receipt.json`
- `src/structural_analysis/schemas/hip_sparse_lu_apply_compile_receipt_v1.schema.json`
- `scripts/run_engine_v2_hip_sparse_lu_apply.py`
- `implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp`
- `implementation/phase1/release_evidence/productization/engine_v2_hip_current_tangent_operator_compile_receipt.json`
- `src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py`
- `src/structural_analysis/schemas/hip_current_tangent_operator_compile_receipt_v1.schema.json`
- `scripts/run_engine_v2_hip_current_tangent_operator.py`
- `src/structural_analysis/engine_v2/cpu_fgmres_checkpoint.py`
- `src/structural_analysis/schemas/cpu_fgmres_checkpoint_v1.schema.json`

Build and check the compile-only receipt without opening a GPU device:

```bash
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_recurrence.py \
  --compile-only --architecture gfx1030
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_recurrence.py \
  --compile-only --check
PYTHONPATH=src python3 scripts/run_engine_v2_hip_sparse_lu_apply.py \
  --compile-only --check
PYTHONPATH=src python3 scripts/run_engine_v2_hip_current_tangent_operator.py \
  --compile-only --check
```

Run actual local hardware and then check the source-bound runtime receipt:

```bash
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_recurrence.py
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_recurrence.py --check
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_device_receipt.py \
  --out implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_gfx1030_device_receipt.json \
  --check
PYTHONPATH=src python3 scripts/build_engine_v2_hip_fgmres_stage4_status.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py \
  tests/test_engine_v2_hip_fgmres_recurrence.py \
  tests/test_engine_v2_hip_fgmres_recurrence_runner.py
```

A clean hardware operator creates an unsigned architecture-neutral receipt and
the exact detached-signature payload with:

```bash
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_device_receipt.py \
  --out <device-receipt.json> \
  --wheel <same-wheel.whl> \
  --organization-id <organization> \
  --runner-id <runner> \
  --execution-location <location> \
  --signing-payload-out <payload.json>
```

The independent `gfx1100` operator also passes
`--independent-from-local-gfx1030`. After an operator-controlled signer creates
the detached Ed25519 signature, attach and verify it without exposing the
private key:

```bash
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_device_receipt.py \
  --out <device-receipt.json> \
  --attach-signature <signature.bin> \
  --public-key <public-key.pem> \
  --signer-id <signer>
PYTHONPATH=src python3 scripts/run_engine_v2_hip_fgmres_device_receipt.py \
  --out <device-receipt.json> --check
```

## Claim boundary

Both receipts remain `status=partial`. The current runtime proof covers a small
66-equation fixture with a fixed launch schedule, an operator-derived
left-scaled Jacobi preconditioner, and restart length capped at 32. It verifies
the Jacobi apply and recurrence bytes for this fixture but does not close
production-scale preconditioner effectiveness or a
production-scale multi-block operator, scalable checkpoint/recovery, production
preconditioner breadth, independent `gfx1100` run, clean same-commit and wheel
identity across devices, signed receipt pair, or model-size performance sweep.
These limits prevent promotion to production HIP readiness or G1 closure.
