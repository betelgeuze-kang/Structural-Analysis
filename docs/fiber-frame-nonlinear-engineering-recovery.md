# Fiber-frame nonlinear engineering recovery

This slice adds the source-specific exact recovery path for the bounded
stateful RC fiber frame. Its implementation is
`src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_recovery.py`.

The J5-backed `NonlinearNumericalResultIR` remains authoritative only for
convergence, displacement, and committed material state. Reactions and
engineering forces become authoritative only in the
`FiberFrameNonlinearEngineeringResultIR` produced by this operator.

## Exact terminal replay

The operator does not copy force, reaction, section, stress, or energy arrays
from the terminal Newton result. It starts from:

- the last accepted parent checkpoint;
- the terminal J3 solver generalized-coordinate bytes;
- the exact bounded frame problem, J1 topology, and J2 scaling;
- the terminal J4 constituent-state bundle and J5 convergence receipt.

It then reruns the terminal constitutive transition and independently rebuilds
the engineering path:

```text
terminal parent checkpoint + J3 terminal coordinates
  -> constitutive integration at ordered section fibers
  -> section axial force and moment from fiber stress x area
  -> member local end force from B-transpose section integration
  -> fixed-chord local/global transformation
  -> element-to-global scatter
  -> canonical six-DOF SI residual
  -> free-equation equilibrium + authored-fixed reaction partition
```

Every replayed element, section, and constituent state must match the terminal
checkpoint bytes. Every constituent byte payload must also match the ordered
terminal `MaterialStateBundle` entry. The fiber output order is required to
equal the material-projection `source_identity_hash`.

## Consistency gates

The result is fail-closed unless all of these checks pass:

- J5-scaled free residual at or below the source tolerance;
- element/global scatter, local/global force, section integration, and section
  resultant scaled errors at or below `1e-12`;
- fiber strain error at or below `1e-15`;
- local/global work, section/element work, and dissipated-energy balance at or
  below `1e-12`;
- fixed-chord transformation orthogonality at or below `1e-12`;
- exact terminal element, section, constituent, and material-bundle bytes.

The retained arrays use immutable little-endian byte backing. JSON manifests
contain descriptors, dimensions, units, order hashes, byte lengths, data
hashes, content hashes, and artifact URIs, but never the raw arrays or
constituent-state bytes.

## Bounded authority

The source-specific engineering result promotes authority only for:

- authored-fixed reactions in canonical six-DOF SI order;
- member local end forces;
- ordered section generalized strains and resultants;
- ordered fiber strains, stresses, and dissipated-energy observations.

It does not promote geometric nonlinearity, releases, offsets, distributed
loads, nonzero prescribed displacement, arbitrary topology, sparse/HIP parity,
design-code checks, viewer output, release readiness, or commercial use. The
generic nonlinear recovery candidate remains deliberately non-authoritative
and still rejects adapter-bound fiber-frame numerical results.

## Validation levels

`validate_fiber_frame_nonlinear_recovery_operator_shape` checks immutable
storage, descriptor identities, source bindings, array semantics, reaction
partitioning, consistency gates, and the canonical operator hash.

`validate_fiber_frame_nonlinear_recovery_operator` additionally replays the
complete terminal engineering path and compares every retained artifact.

`validate_fiber_frame_nonlinear_engineering_result_ir` validates the exact
source adapter, recovery operator, promoted authority, and result hash. The two
manifest validators enforce strict finite JSON, exact keys, descriptor-only
storage, canonical hashes, and nested source/operator cross-bindings.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_nonlinear_recovery.py \
  tests/test_stateful_fiber_frame2d_nonlinear_result_adapter.py \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_recovery.py \
  tests/test_stateful_fiber_frame2d_nonlinear_recovery.py
```
