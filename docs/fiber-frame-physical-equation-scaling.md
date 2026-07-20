# Fiber-frame physical EquationScaling and residual trace

## Scope

PR-J2 adds the physical force/moment scaling layer required by issue #133. It
consumes the merged J1 `FiberFrameNonlinearExecutionTopologyPlan v1` and
produces two non-authoritative contracts:

- `FiberFramePhysicalEquationScalingBinding v1`;
- `FiberFramePhysicalResidualTrace v1`.

The binding embeds an unchanged Engine v2 `EquationScaling v1` artifact and
binds it to the exact J1 topology-plan hash. It does not call
`bind_equation_scaling_to_execution_plan`, synthesize a linear-static
`ExecutionPlan v1`, or describe the nonlinear constitutive state as StateIR v1.
Existing ExecutionPlan v1, StateIR v1, schemas, capability profiles, and golden
hashes are unchanged.

## Source-unit boundary

The bounded fiber-frame source uses node-major physical equations
`[UX, UY, RZ]` with:

- translational forces in kN;
- rotational moments in kN·m.

J2 fixes the versioned adapter profile
`stateful_fiber_frame2d_kn_kn_m_to_si.v1`:

```text
force_N   = 1000 * force_kN
moment_Nm = 1000 * moment_kNm
```

The source vector is mapped through the J1 solver-to-physical equation map into
canonical node order `[UX, UY, UZ, RX, RY, RZ]`. Inactive `UZ`, `RX`, and `RY`
entries remain exact zero. The binding retains immutable SI coordinates,
reference loads, and scale divisors with raw-byte and metadata-plus-byte hashes.

## Engine v2 policy reuse

The existing Engine v2 policies apply without changing v1 semantics. J2 lifts
the 2D node coordinates into SI 3D coordinates with exact `z=0` and uses:

```text
characteristic-length policy = two_max_radius_from_fsum_centroid.v1
reference-force policy       = max_translation_or_equivalent_moment_with_floor.v1
reference equation scope     = free_equations

x_bar  = fsum(x_i) / node_count
L_char = 2 * max_i(norm(x_i - x_bar))

F_ref = max(F_min,
            max(abs(free translational reference loads in N)),
            max(abs(free rotational reference loads in N*m)) / L_char)

divisor(UX, UY, UZ) = F_ref
divisor(RX, RY, RZ) = F_ref * L_char
```

Constrained-equation loads are committed as source bytes but cannot set
`F_ref`. A topology with no free physical equations fails closed and remains a
separate no-solve/reaction-only path.

The embedded `structural-analysis-equation-scaling.v1` source commitment binds:

- J1 topology-plan hash as its exact base-plan identity;
- ModelIR content hash and frame case ID;
- an Engine-compatible content hash of the exact physical free-DOF vector;
- canonical equation-order hash;
- SI coordinate and reference-load descriptors and hashes;
- policy names, explicit minima, characteristic length, reference force, and
  scale-vector bytes.

The outer J2 binding additionally records the original J1
`free_physical_dofs` descriptor hash and the explicit source-unit profile. Full
object validation replays the J1 plan against the source problem and derives
the complete embedded EquationScaling artifact again. Descriptor-only manifest
validation establishes schema and hash consistency but does not claim access to
external source bytes.

## Residual observation

`trace_stateful_fiber_frame2d_physical_residual` accepts one source physical
residual in `[UX kN, UY kN, RZ kN*m]` order. It retains:

- the exact source 3-DOF vector;
- the canonical six-DOF SI residual;
- the dimensionless scaled residual;
- the exact J1 free physical equation set;
- separate raw translation L2/L∞ norms in N;
- separate raw rotation L2/L∞ norms in N·m;
- dimensionless scaled L2/L∞ norms;
- governing equation, node ID, and physical DOF;
- characteristic length, reference force, topology hash, binding hash,
  EquationScaling hash, and source-commitment hash.

Ties in absolute scaled residual choose the smallest free physical equation.
There is deliberately no raw norm over mixed N and N·m values. The trace has no
`converged`, terminal, backend, hardware, reaction/member-force authority, or
ResultIR field.

Actual source assembly replay uses:

```python
physical_source_residual = (
    assembly.internal_loads_global - assembly.external_loads_global
)
trace = trace_stateful_fiber_frame2d_physical_residual(
    topology_plan=plan,
    scaling_binding=binding,
    raw_residual_source_3dof=physical_source_residual,
)
```

This observes the same `internal_minus_external` physical residual that the
current solver converts into generalized Newton coordinates. Solver-coordinate
scaling from J1 and physical force/moment nondimensionalization from J2 remain
separate contracts.

## Persistence and fail-closed checks

Binding source/scale arrays and all trace vectors have canonical little-endian
fp64 immutable storage. External bytes can be checked independently with:

```python
validate_fiber_frame_physical_equation_scaling_array_bytes(...)
validate_fiber_frame_physical_residual_trace_array_bytes(...)
```

Validators reject stale or coherently rehashed substitutions of unit profiles,
Engine schema/policies, topology/scaling/source hashes, descriptor metadata,
SI conversion, active equations, dimensional/scaled norms, governing DOF, and
authority flags. Full replay against the source problem rejects a binding made
for another geometry, load vector, free partition, node order, or topology
plan.

## Direct API

```python
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
    trace_stateful_fiber_frame2d_physical_residual,
)
```

The module remains a direct import and is not re-exported through
`structural_analysis.assembly`.

## Authority and next step

J2 establishes physical SI equation scaling and non-authoritative residual
observation only. It grants no convergence, nonlinear numerical-result,
reaction/member-force/fiber engineering, design/code, release, or commercial
authority.

PR-J3 adds the typed
[`checkpoint-chain → nonlinear kinematic-state chain`](fiber-frame-nonlinear-kinematic-state-chain.md),
including exact physical/generalized/canonical displacement mapping and
accepted → transient-trial → committed ancestry. PR-J4 now binds this J2
scaling identity, that exact J3 chain, and PR #132's MaterialStateProjectionChain
in the
[`FiberFrameNonlinearExecutionStateBinding`](fiber-frame-nonlinear-execution-state-binding.md).
Only the later nonlinear terminal and exact recovery contracts may connect this
path to ResultIR authority.

## Verification

Focused tests cover deterministic policy values, kN/kN·m to SI conversion,
translation- versus moment-governed reference force, constrained-load exclusion,
explicit minima, fully constrained no-solve handling, actual assembly residual
replay, separated dimensional norms, deterministic governing ties, immutable
arrays, external-byte validation, strict manifests, coherent tamper rejection,
and cross-artifact source replay.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_physical_equation_scaling.py \
  tests/test_stateful_fiber_frame2d_execution_topology.py \
  tests/test_engine_v2_equation_scaling_v1.py
```
