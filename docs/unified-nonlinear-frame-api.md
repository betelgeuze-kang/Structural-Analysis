# Unified Nonlinear Frame API

`analyze_nonlinear_frame` and `structural-analysis-nonlinear-frame` select one
explicit analysis profile while returning the same typed envelope and normalized
SI field names.

| Profile | Current boundary |
| --- | --- |
| `fixed_chord_serial_cantilever.v1` | Existing bounded serial-cantilever Developer Preview |
| `corotational_one_bay_portal.v1` | Four-node, three-member rectangular portal candidate |
| `corotational_connected_frame2d.v1` | Connected 2–128-node, 1–256-member planar graph candidate |

The portal compiler requires exactly two fully fixed bases. The connected-frame
compiler accepts branching topology, multiple support nodes with arbitrary
`UX`/`UY`/`RZ` subsets, proportional nodal loads, and load-factor-proportional
prescribed values on constrained components. Both require explicit rectangular
RC fiber sections and the supported steel/concrete laws. Unsupported keys,
topology, support, load, material, section, unit, or coordinate semantics fail
before solve.

For a ready corotational result, the API binds:

1. the canonical model checksum and selected compiler hash;
2. J1-J5 topology, scaling, state ancestry, solver-state, and convergence receipts;
3. exact terminal-parent engineering replay and immutable SI artifacts;
4. a complete epoch-zero-rooted checkpoint-chain hash and canonical artifact bytes;
5. normalized displacement, reaction, member, section, and fiber rows;
6. an explicit dense or native COO/CSR backend choice with no fallback.

The corotational profile accepts `numpy_linalg_solve_dense` or
`scipy_sparse_spsolve_cpu`. The sparse selector scatters member tangents directly
to COO and canonical sorted CSR, then applies unregularized SuperLU/COLAMD with a
schema-validated exact conditioning receipt for every factorization; see
[Corotational Fiber-Frame Native Sparse Assembly](corotational-fiber-frame-native-sparse.md).
The fixed-chord profile remains dense-only.

The connected profile additionally accepts dense direct displacement control
through the same Python entry point and result envelope:

```python
result = analyze_nonlinear_frame(
    model,
    NonlinearFrameConfig(
        profile="corotational_connected_frame2d.v1",
        control_mode="direct_displacement_control",
        control_node_id="N2",
        control_dof="UX",
        target_control_displacements_m=(2.5e-5, 5.0e-5),
    ),
)
```

The selected coordinate must be one free `UX` or `UY` DOF. The augmented dense
Newton solve treats the proportional load factor as an unknown and requires the
equilibrium, control, increment, material-validity, line-search, no-fallback, and
no-regularization gates. Its accepted path is normalized into the same exact
terminal-parent engineering recovery and epoch-zero checkpoint chain used by
load control. Restart artifacts are replayed from genesis byte-for-byte before
remaining displacement targets execute.

The same coordinate fields select bounded spherical arc-length continuation:

```python
result = analyze_nonlinear_frame(
    model,
    NonlinearFrameConfig(
        profile="corotational_connected_frame2d.v1",
        control_mode="arc_length",
        control_node_id="N2",
        control_dof="UY",
        target_control_displacements_m=(-0.03,),
    ),
)
```

Arc-length results retain every committed frame state in an epoch-zero chain
and the terminal continuation direction, radius, cumulative progress, and
accepted/rejected counts in one canonical composite checkpoint. A supplied
artifact is cross-validated and then reproduced from genesis byte-for-byte.
Only after that replay does the common exact engineering recovery expose the
terminal displacement, reaction, member, section, and fiber results.

A fully constrained connected-frame model with only prescribed values follows a
reaction-only no-solve contract. It commits the proportional checkpoint path and
exact recovery without Newton iterations or a convergence claim; sparse
factorization diagnostics are correctly inapplicable on that path.

When a restart artifact is supplied, every prefix step is solved again from
genesis and its checkpoint bytes must match before any remaining step runs. A
valid terminal chain therefore replays to identical engineering output. Altered
bytes, model identity, load prefix, parent link, state hash, or non-canonical JSON
fail closed.

The command line writes result, report, and optional checkpoint files atomically:

```bash
structural-analysis-nonlinear-frame \
  examples/public_corotational_branching_frame.json \
  --profile corotational_connected_frame2d.v1 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out result.json \
  --report-out report.json \
  --checkpoint-out checkpoint-chain.json
```

Control modes use the same command and output bundle. For example:

```bash
structural-analysis-nonlinear-frame model.json \
  --profile corotational_connected_frame2d.v1 \
  --control-mode arc_length \
  --control-node-id N2 \
  --control-dof UY \
  --target-control-displacement -0.03 \
  --checkpoint-out arc-checkpoint.json \
  --out arc-result.json \
  --report-out arc-report.json
```

The durable Job Service accepts the same exact direct/arc configuration. A
control job executes atomically, publishes its terminal checkpoint, result, and
validation evidence as content-addressed artifacts, and binds all three hashes
in the completion transaction. Workbench verifies the referenced result/evidence
pair and displays control, terminal, recovery, fallback, and result-row values
with explicit `available`, `unavailable`, or `invalid` states; it never infers
solver truth from orchestration status.

The same envelope preserves the existing fixed-chord authority while converting
fiber stress output from MPa to Pa. The corotational endpoints remain bounded
Developer Preview candidates. Parallel members, disconnected graphs,
production-scale conditioning, density-derived self-weight, arbitrarily rotated
local axes, native sparse augmented control execution, both independent Level 2
comparisons, design-code authority, and release promotion remain separate gates.

The connected profile does execute finite rigid offsets, optional RZ end
releases, uniform dead loads in explicitly declared chord-bound member-local
axes, and self-weight derived from explicit SI mass-per-length and global gravity
inputs. Those features use the same exact checkpoint replay and engineering
recovery gates as the remaining connected-frame path.
