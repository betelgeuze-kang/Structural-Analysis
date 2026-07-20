# Engine v2 nonlinear result and recovery contracts

## Purpose

This slice separates three different claims that must not share one `PASS`:

1. a converged committed nonlinear numerical/material state;
2. a reaction/member-force recovery candidate assembled from element forces;
3. authoritative nonlinear engineering-result recovery.

Only the first is granted authority by this contract family. The second is
explicitly non-authoritative, and the third remains future work.

## Nonlinear terminal receipt

`NonlinearTerminalReceipt` binds:

- source solver schema and receipt hash;
- replay-verified `EquationScaling` hash;
- exact reduced-CSR identity;
- exact source free-solution bytes hash;
- source-solver coordinate-scaling receipt hash;
- exact committed `StateIR` hash;
- exact committed `MaterialStateBundle` hash;
- accepted path-history hash;
- residual and increment values and tolerances;
- accepted, rejected, and rollback counts;
- fallback and regularization counts.

Creation fails unless:

```text
terminal_reason = converged_residual_and_increment
converged = true
final residual <= residual tolerance
final increment <= increment tolerance
accepted step count > 0
rollback count <= rejected attempt count
fallback count = 0
regularization count = 0
```

Attaching the receipt to a result additionally requires its accepted-step
count to equal the committed StateIR and material-bundle epoch.

The residual norm is explicitly the dimensionless equation-scaled free-DOF
infinity norm. The increment norm is explicitly a dimensionless
source-solver-coordinate-scaled free-DOF infinity norm. The latter remains an
opaque receipt binding in this generic contract; a concrete solver adapter must
replay that scaling before it can create a trusted terminal receipt.

## NonlinearNumericalResultIR

The legacy result construction path requires:

- exact validated `ExecutionPlan`;
- replay-verified `EquationScaling` bound to that plan;
- exact `ExecutionPlanReducedCSR` identity with a solved free-equation space;
- positive-epoch committed `StateIR`;
- committed `MaterialStateBundle` at the same epoch;
- material bundle bound to the same model, plan, and solver state;
- terminal receipt bound to that exact state and material bundle;
- independent full-residual and boundary-condition receipt hashes;
- declared backend role and receipt;
- canonical global displacement artifact descriptor.

The exact committed StateIR free-displacement bytes must match the source
solution hash carried by the terminal receipt. Imported manifests additionally
enforce `dof_count`, displacement shape, byte length, and canonical artifact URI
coherence after schema validation.

A concrete nonlinear solver whose committed state cannot honestly be encoded
as the current stateless-linear-elastic `StateIR v1` may instead implement the
`NonlinearNumericalResultSourceAdapter` replay protocol. The adapter must return
a fully validated source-neutral snapshot containing the same normalized result
bindings and immutable canonical displacement bytes. The result retains that
adapter and replays it on every in-memory validation; mixing adapter and legacy
source objects is rejected. Existing legacy manifests and hashes are unchanged,
while the exact claim boundary records whether the fiber-frame kinematic
adapter path was used.

The authority axes are:

```text
numerical state   authoritative
convergence       authoritative
displacement      authoritative
material state    authoritative
reaction          not evaluated
member force      not evaluated
integration-point engineering output  not evaluated
```

Design, code-compliance, release, and commercial authority remain false.
"Material state" here means the exact terminal ordered bytes bound to the
committed numerical state. This contract does not replay constitutive laws or
the complete material-state history.

The manifest is descriptor-only. External displacement bytes are validated
against exact byte length and data hash.

## NonlinearRecoveryCandidateIR

The bounded recovery candidate accepts:

- exact source `NonlinearNumericalResultIR`;
- global external and global internal force vectors;
- element-to-global DOF indices;
- element global force vectors;
- one member axial-force value per element;
- a recovery-law receipt hash.

The generic candidate currently accepts only the legacy ExecutionPlan/StateIR
source profile. Adapter-bound results fail closed with
`nonlinear_recovery_source_profile_unsupported`; they need a source-specific
exact recovery operator and cannot borrow reaction or member-force authority
from the generic scatter check.

It independently scatters element forces and requires agreement with the
supplied global internal vector after applying the bound per-equation scaling.
It then forms

```text
R = F_internal - F_external
```

It scales that SI residual with the exact `EquationScaling` retained by the
source result, then checks the free-equation dimensionless infinity norm
against the source nonlinear terminal tolerance. Constrained SI residual is
partitioned as a reaction candidate.

This remains non-authoritative because the candidate does not recompute element
forces from exact geometry, committed integration-point state, and constitutive
law. Hashing a recovery-law receipt is not equivalent to replaying or
authenticating the law.

## Required follow-up for engineering authority

A future `NonlinearRecoveryOperator` must bind and replay:

- exact element geometry/current configuration;
- exact integration-point order and committed material bytes;
- element kinematics and constitutive/recovery law versions;
- local/global transformations;
- internal force, member force, stress/strain, and dissipated energy;
- element-to-global equilibrium;
- CPU/HIP parity where claimed.

Only then may reaction, member force, or integration-point output become
authoritative.

## Current exclusions

- no adapter from the public two-bar API yet;
- no nonlinear artifact writer or Viewer projection;
- no shell/fiber/frame engineering recovery;
- no fiber-frame kinematic/coordinate-scaling adapter authority (issue #133);
- no receipt signature/authenticity verification;
- no design/code or commercial authority;
- no G1 closure.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py \
  tests/test_engine_v2_nonlinear_recovery_source_binding.py \
  tests/test_engine_v2_core_dependency_boundary.py \
  tests/test_verify_quality_gate_contract.py
python3 -m ruff check \
  src/structural_analysis/engine_v2/contracts/nonlinear_result.py \
  src/structural_analysis/engine_v2/contracts/nonlinear_recovery.py \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py \
  tests/test_engine_v2_nonlinear_recovery_source_binding.py
```
