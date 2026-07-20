# Engine v2 nonlinear result and recovery contracts

## Purpose

This slice separates three different claims that must not share one `PASS`:

1. a converged committed nonlinear numerical/material state;
2. a reaction/member-force recovery candidate assembled from element forces;
3. authoritative nonlinear engineering-result recovery.

Only the first is granted authority in this PR. The second is explicitly
non-authoritative, and the third remains future work.

## Nonlinear terminal receipt

`NonlinearTerminalReceipt` binds:

- source solver schema and receipt hash;
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
fallback count = 0
regularization count = 0
```

## NonlinearNumericalResultIR

The result requires:

- exact validated `ExecutionPlan`;
- positive-epoch committed `StateIR`;
- committed `MaterialStateBundle` at the same epoch;
- material bundle bound to the same model, plan, and solver state;
- terminal receipt bound to that exact state and material bundle;
- independent full-residual and boundary-condition receipt hashes;
- declared backend role and receipt;
- canonical global displacement artifact descriptor.

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

It independently scatters element forces and requires agreement with the
supplied global internal vector. It then forms

```text
R = F_internal - F_external
```

and checks free-equation equilibrium against the source nonlinear terminal
tolerance. Constrained residual is partitioned as a reaction candidate.

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
- no receipt signature/authenticity verification;
- no design/code or commercial authority;
- no G1 closure.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_material_state_bundle_v1.py \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py
python3 -m ruff check \
  src/structural_analysis/engine_v2/contracts/material_state_bundle.py \
  src/structural_analysis/engine_v2/contracts/nonlinear_result.py \
  src/structural_analysis/engine_v2/contracts/nonlinear_recovery.py \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py
```
