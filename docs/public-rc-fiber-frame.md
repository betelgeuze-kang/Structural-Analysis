# Public bounded RC fiber-frame API and CLI

## Purpose

This Developer Preview slice connects a neutral `CanonicalModel` to the
stateful RC fiber-frame solver, its complete checkpoint ancestry, the J1--J5
terminal contracts, and exact engineering recovery. It is a deliberately
narrow serial-cantilever product path, not a general nonlinear frame solver.

The runnable input example is
[`examples/public_rc_fiber_frame_cantilever.json`](../examples/public_rc_fiber_frame_cantilever.json).

## Python API

```python
from structural_analysis.api import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    load_model,
    validate_public_rc_fiber_frame_result,
)

model = load_model("examples/public_rc_fiber_frame_cantilever.json")
result = analyze_public_rc_fiber_frame(
    model,
    PublicRCFiberFrameConfig(load_steps=4),
)
report = validate_public_rc_fiber_frame_result(result)

if report.contract_pass:
    checkpoint_bytes = result.checkpoint_artifact()
```

`checkpoint_artifact(epoch)` can export any accepted prefix from epoch zero
through the terminal epoch. The returned bytes use the existing canonical,
schema-validated checkpoint-chain format.

To resume from an exact prefix:

```python
prefix = result.checkpoint_artifact(epoch=2)
resumed = analyze_public_rc_fiber_frame(
    model,
    PublicRCFiberFrameConfig(load_steps=4),
    restart_checkpoint_chain=prefix,
)
```

The restart is accepted only when all of the following match exactly:

- problem contract and case identity;
- epoch-zero genesis and complete parent ancestry;
- configured load-factor prefix;
- replayed checkpoint canonical bytes, including every member, section, and
  constituent state.

A valid prefix is replayed before remaining steps execute. A different model,
load schedule, material parameter, section discretization, or altered byte
fails closed before continuation.

## CLI

After editable installation, either the console script or module entry point
can be used:

```bash
structural-analysis-nonlinear-fiber-frame \
  examples/public_rc_fiber_frame_cantilever.json \
  --load-steps 4 \
  --out result.json \
  --report-out validation-report.json \
  --checkpoint-out checkpoint-chain.json
```

```bash
python -m structural_analysis.api.nonlinear_fiber_frame_cli \
  examples/public_rc_fiber_frame_cantilever.json \
  --restart-from checkpoint-prefix.json \
  --load-steps 4 \
  --out resumed-result.json \
  --report-out resumed-report.json \
  --checkpoint-out resumed-checkpoint-chain.json
```

Output and protected input paths are resolved before model loading. Result,
report, and checkpoint outputs must be distinct, non-nested regular-file
targets and may not alias either the model or restart input. When a checkpoint
is available, all three outputs are staged before replacement and use bounded
best-effort rollback if replacement fails. If an execution has no checkpoint,
the result and report are replaced together and any stale checkpoint target is
removed so an older artifact cannot be mistaken for the current run.

## Exact accepted model profile

The public compiler profile is
`planar_serial_cantilever_explicit_rectangular_rc.v1`.

### Geometry and topology

- units are exactly `m` and `kN`;
- coordinate order is `XYZ`, with `Z` up and every node at exactly `Z = 0`;
- 2--16 nodes and exactly `node_count - 1` members;
- one connected, acyclic, unbranched chain; node degree may not exceed two;
- one endpoint support restraining exactly `UX`, `UY`, and `RZ` at zero;
- no duplicate node coordinates, IDs, member IDs, or parallel connectivity.

This chain may be straight or piecewise non-collinear. Branches, portals,
closed loops, arbitrary support layouts, releases, offsets, diaphragms, rigid
links, and general topology are not compiled by v1.

### Members and sections

Every member row has exactly:

```text
id, type, nodes, section, integration_order
```

`type` is `stateful_rc_fiber_frame2d`, and `integration_order` is 2 or 3.
Every section row has exactly the fields shown in the example and uses
`type = rectangular_rc_fiber_section`. Width, depth, cover, layer count, top
and bottom bar count, bar area, and both material references are explicit.
Concrete discretization is bounded to 2--32 layers and reinforcement to 1--64
bars per lumped top or bottom layer.

Every declared section and material must be used. Unused rows do not silently
survive compilation.

### Materials

The only accepted profiles are:

- `bilinear_combined_hardening_steel`, with explicit elastic modulus, yield
  stress, isotropic and kinematic hardening moduli, and yield tolerance;
- `asymmetric_concrete_damage`, with explicit elastic modulus, tensile and
  compressive strengths, tensile and compressive softening rates, and history
  tolerance.

All values are finite and sign/range checked. No defaults are inferred by the
public compiler.

### Loading

Loads form one reference pattern multiplied by monotonically increasing
factors `1/load_steps ... 1.0`. There are 2--64 accepted load steps and at
least one nonzero load row away from the fixed endpoint. Every load row
contains exactly `FX/FY/FZ/MX/MY/MZ`; `FZ`, `MX`, and `MY` must be exactly
zero. Distributed loads, multiple cases, imposed motion, cyclic schedules,
and arc length are outside v1.

## Solve, state, and result authority

The dense CPU Newton path commits global displacement and all member, section,
and constituent states atomically, or retains the exact accepted checkpoint
after failure. Fallback and regularization cannot promote a ready result.

A final public result becomes `ready` only after it builds and validates:

```text
canonical input checksum
  -> bounded StatefulFiberFrame2DProblem
  -> complete epoch-zero checkpoint chain
  -> J1 six-DOF topology
  -> J2 physical equation scaling
  -> J3 kinematic state chain
  -> J4 material-state projection and combined binding
  -> J5 full-load terminal receipt
  -> NonlinearNumericalResultIR adapter
  -> exact source-specific engineering recovery
```

The serialized result includes:

- all-node canonical six-DOF displacements;
- authored support reactions in SI units;
- member local end forces;
- ordered Gauss-point strain, curvature, axial force, moment, and energy;
- ordered fiber identity, location, area, strain, stress, and dissipated energy;
- convergence observations, checkpoint descriptor, and all major contract
  hashes.

Reaction, member-force, section-resultant, and fiber strain/stress authority
comes only from exact recovery. Design and commercial authority remain false.
Raw checkpoint bytes are not embedded in result JSON; they are obtained with
`checkpoint_artifact()` or `--checkpoint-out` and are bound by byte length and
SHA-256 artifact hash.

## Failure behavior

Unsupported input returns a deterministic `blocked` result with
`solver_executed = false`. A Newton failure returns `blocked`, records exact
rollback status, and retains the last committed checkpoint chain. A J1--J5 or
recovery failure also returns `blocked` and never serializes engineering values
as authoritative.

The CLI returns exit code 0 only for a fully authoritative ready result and 2
for a blocked result. Argument, path, or unreadable restart errors use the
standard argparse error exit.

## Explicit non-claims

This slice does not validate or authorize:

- geometric nonlinearity, P-Delta, large rotation, or corotational RC response;
- shear deformation, torsion, bond slip, confinement, fracture-energy
  regularization, or mesh-objective damage;
- releases, offsets, diaphragms, distributed loads, prescribed movement,
  arbitrary topology, sparse execution, or HIP execution;
- design-code checks, member sizing, final-design approval, release readiness,
  commercial use, or G1 closure;
- formal Level 2/3 independent-solver or published-benchmark verification.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_public_rc_fiber_frame_api.py \
  tests/test_stateful_fiber_frame2d_nonlinear_recovery.py

python3 -m ruff check \
  src/structural_analysis/api/nonlinear_fiber_frame.py \
  src/structural_analysis/api/nonlinear_fiber_frame_cli.py \
  tests/test_public_rc_fiber_frame_api.py
```
