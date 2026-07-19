# Phase 2 stateful axial adaptive matrix-free Newton

This slice adds adaptive physical-load stepping and persisted material-state
restart to the bounded axial-chain matrix-free Newton bridge. It builds on the
single-step accepted/trial contract without changing the package-level
`nonlinear` re-export surface.

## Adaptive attempt order

Each physical attempt follows this order:

```text
accepted displacement + accepted material states
  -> target physical load
  -> current-tangent matrix-free Newton step
  -> residual/increment/linear-replay/fallback gates
  -> commit displacement and material states together
     or retain their exact canonical bytes and reduce the step
  -> persist the resulting attempt boundary
```

The controller stores a checkpoint after successful commits and failed
rollbacks. A failed-attempt checkpoint therefore retains both the unchanged
accepted state and the reduced next step size. Cumulative attempt counts,
fallback and regularization counts, rollback status, gate status, and the
attempt budget are also retained so restarting cannot reset a spent budget.

Successful fast steps may grow up to the configured maximum. A final remainder
smaller than the minimum step is allowed when it reaches the target directly;
a failed step whose reduced size falls below the minimum terminates blocked.

## Persisted checkpoint contract

`StatefulAxialAdaptiveMatrixFreeCheckpoint.to_bytes()` emits canonical UTF-8
JSON containing:

- the complete accepted displacement and integration-point material states;
- their deterministic state hashes;
- the next adaptive step size and cumulative progress;
- the source case and source-problem contract hash;
- the adaptive path contract hash; and
- a checkpoint hash over all preceding fields.

The source-problem hash binds mesh topology, constraints, reference loads and
prescribed displacements, element geometry and response kind, and canonical
material class parameters. The path hash additionally binds adaptive policy,
inner Newton policy, and either the default CPU FGMRES configuration or an
explicit custom solver-factory contract hash.

Loading rejects non-canonical JSON, duplicate keys, stale hashes, material
state schema/type mismatches, changed source material parameters, changed path
policy, non-equilibrated accepted state, and exhausted attempt counts outside
the configured bounds. The material-state decoder is driven by each source
element's initial state and covers the existing steel plasticity, concrete
damage, parallel composite, and bilinear-link state dataclasses, including the
nested composite state.

The artifact writer uses exclusive creation and never overwrites an existing
checkpoint. The direct module API is:

```python
from structural_analysis.solvers.nonlinear.stateful_axial_adaptive_matrix_free_newton import (
    StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    adaptive_stateful_axial_matrix_free_newton_continuation,
    load_stateful_axial_adaptive_matrix_free_checkpoint_bytes,
    read_stateful_axial_adaptive_matrix_free_checkpoint_artifact,
    write_stateful_axial_adaptive_matrix_free_checkpoint_artifact,
)
```

## Focused verification

`tests/test_stateful_axial_adaptive_matrix_free_newton.py` covers:

- deterministic large-step rejection followed by exact material-state rollback,
  step reduction, commit, growth, and target completion;
- restart from the checkpoint immediately after a failed attempt, with the same
  cumulative metrics and exact final accepted/material-state bytes as one-shot;
- refusal to reset a consumed maximum-attempt budget after restart;
- exact artifact write/read and refusal to overwrite;
- rejection of byte tamper, non-canonical JSON, source material drift, and path
  policy drift;
- canonical restoration of all four bounded material-state families; and
- mandatory contract hashing for a custom tangent-solver factory.

Run the focused and inherited continuation regression with:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_axial_adaptive_matrix_free_newton.py \
  tests/test_stateful_axial_matrix_free_newton.py \
  tests/test_load_controlled_matrix_free_newton.py
```

## Claim boundary

This is a canonical JSON material checkpoint and local CPU axial-chain
continuation path. It does not make the older displacement-only generic
checkpoint material-aware, and it does not add an arc-length branch,
general-frame/shell integration-point state, production preconditioning,
ROCm/HIP parity, or an authoritative G1 full-building receipt. Those claims
remain false until separately implemented and evidenced.
