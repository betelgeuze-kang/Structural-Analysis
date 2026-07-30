# Unified Nonlinear Frame API

`analyze_nonlinear_frame` and `structural-analysis-nonlinear-frame` select one
explicit analysis profile while returning the same typed envelope and normalized
SI field names.

`analyze_nonlinear_frame_model_ir` accepts only a validated ModelIR v2 document
with capability profile `bounded_planar_frame_alpha`. That profile makes the
nonlinear steel/concrete laws, rectangular RC fiber section, six-DOF constraints,
finite offsets, RZ releases, uniform initial-local dead loads, and one nonlinear
load pattern explicit in canonical SI units. The adapter converts N to kN and Pa
to MPa for the existing bounded solver without inventing absent values.

| Profile | Current boundary |
| --- | --- |
| `fixed_chord_serial_cantilever.v1` | Existing bounded serial-cantilever Developer Preview |
| `corotational_one_bay_portal.v1` | Four-node, three-member rectangular portal candidate |
| `corotational_connected_frame2d.v1` | Connected 2–128-node, 1–256-member planar graph candidate |

The portal compiler requires exactly two fully fixed bases. The connected-frame
compiler accepts branching topology, multiple support nodes with arbitrary
`UX`/`UY`/`RZ` subsets, proportional nodal loads, and load-factor-proportional
prescribed values on constrained components. It also executes bounded finite
rigid offsets, RZ end releases, and uniform member dead loads in each member's
initial local axes. Both require explicit rectangular RC fiber sections and the
supported steel/concrete laws. Unsupported keys, topology, support, load,
material, section, unit, or coordinate semantics fail before solve.

For a ready corotational result, the API binds:

1. the canonical model checksum and a profile-specific fail-closed model-adapter hash;
   ModelIR entry additionally binds the source content, semantic, provenance, and
   typed adapter-receipt hashes;
2. exact nonlinear topology, DOF ordering, solver-coordinate scaling, and member-feature hashes;
   ModelIR entry wraps these in a typed bounded nonlinear ExecutionPlan receipt
   whose topology/ordering axes are source-bound while convergence and result
   authority remain explicitly absent;
3. source-bound six-DOF physical equation scaling and a terminal free-equation residual trace;
4. J1-J5 state ancestry, solver-state, and convergence receipts;
5. exact terminal-parent engineering replay and immutable SI artifacts;
6. a complete epoch-zero-rooted checkpoint-chain hash and canonical artifact bytes;
7. a typed `corotational-fiber-frame2d-engineering-result-ir.v1` manifest whose
   result, array-bundle, quantity-catalog, and authority hashes are cross-bound
   to the unified result;
8. normalized displacement, reaction, member, section, and fiber rows projected
   from that retained engineering ResultIR;
9. an explicit dense or native COO/CSR backend choice with no fallback.

Direct CanonicalModel calls retain the original profile-adapter identity. The
ModelIR entry uses the separate `bounded_planar_frame_alpha` schema branch and
binds its actual content hash into the nonlinear topology plan. It does not
reinterpret the existing `engine_v2_phase0_linear_3d` profile or synthesize a
linear-static Engine v2 `ExecutionPlan v1` for nonlinear constitutive state.

The corotational profile accepts `numpy_linalg_solve_dense` or
`scipy_sparse_spsolve_cpu`. The sparse selector scatters member tangents directly
to COO and canonical sorted CSR, then applies unregularized SuperLU/COLAMD with a
schema-validated exact conditioning receipt for every factorization; see
[Corotational Fiber-Frame Native Sparse Assembly](corotational-fiber-frame-native-sparse.md).
The fixed-chord profile remains dense-only.

A fully constrained connected-frame model with only prescribed values follows a
reaction-only no-solve contract. It commits the proportional checkpoint path and
exact recovery without Newton iterations or a convergence claim; sparse
factorization diagnostics are correctly inapplicable on that path.

An external-load-free prescribed-motion model with remaining free equations is
blocked before Newton with
`corotational_equation_scaling_unavailable` at
`/solver/equation_scaling`. Prescribed motion is not converted into an invented
force scale. This path remains unsupported until a source-bound kinematic
reference-force contract is implemented.

Every blocked unified result exposes two distinct unsupported identifiers.
`kind` is the detailed diagnostic and may grow as the bounded compiler gains
new fail-closed checks. `reason_code` is the stable routing contract:

| `reason_code` | Meaning |
| --- | --- |
| `input_contract_unsupported` | Input shape, identity, topology, or value violates the selected profile |
| `profile_feature_unsupported` | The input requests a feature outside the bounded profile |
| `equation_scaling_unavailable` | No source-bound physical scale exists for an iterative solve |
| `mechanism_detected` | A singular tangent occurs in a model containing explicit RZ end releases; the trial is rejected without fallback or regularization |
| `restart_artifact_invalid` | Checkpoint bytes or replay ancestry fail exact validation |
| `singular_system_detected` | A singular tangent occurs without an explicit released-member mechanism; the trial is rejected without fallback or regularization |
| `solver_execution_failed` | A supported compiled problem failed before an exact commit |
| `source_model_unsupported` | The canonical source already carried an unsupported declaration |

Each row also requires a JSON-pointer-like `path` and nonempty `detail`. Extra
source diagnostics are preserved under `source_context`; unknown top-level
fields and unknown `reason_code` values are schema-invalid.

When a restart artifact is supplied, every prefix step is solved again from
genesis and its checkpoint bytes must match before any remaining step runs. A
valid terminal chain therefore replays to identical engineering output. Altered
bytes, model identity, load prefix, parent link, state hash, or non-canonical JSON
fail closed.

The durable Job Service publishes the unified result and validation evidence as
one content-addressed pair. Workbench treats the engineering ResultIR manifest
as the typed result authority: it verifies the raw artifact hashes, complete
manifest shape, array-descriptor bundle hash, unified-result bindings, every
engineering authority axis, and the core validation report's exact result hash,
profile, recovery, replay, fallback, and regularization gates before reporting
the pair as verified. The durable reader returns only the ResultIR manifest; it
does not expose or infer solver truth from legacy normalized display rows.

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

The bounded ModelIR sample uses the same command with the connected profile:

```bash
structural-analysis-nonlinear-frame \
  examples/bounded_planar_frame_alpha.model-ir.v2.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 2 \
  --residual-tolerance 1e-9 \
  --out model-ir-result.json \
  --report-out model-ir-report.json \
  --checkpoint-out model-ir-checkpoint-chain.json
```

The distribution boundary is checked from an installed wheel, outside the source
tree, with:

```bash
python scripts/verify_bounded_planar_wheel_smoke.py --json
```

The smoke builds with `--no-build-isolation`: the selected Python environment
must already contain the build-system requirements from `pyproject.toml`. This
keeps the verification path independent of package-index availability while
still installing and executing the resulting wheel outside the source tree.

That smoke requires the wheel to contain the ModelIR schema and bounded planar
adapter, then executes both the member-feature and prescribed-settlement samples
and verifies each source binding, typed engineering ResultIR, exact checkpoint
replay, and exact engineering recovery.
The Ubuntu/Windows and Python 3.10/3.12 determinism workflow runs this packaging
smoke at every coordinate before comparing the frozen result and checkpoint
hashes.

The same envelope preserves the existing fixed-chord authority while converting
fiber stress output from MPa to Pa. The corotational endpoints remain bounded
Developer Preview candidates. Parallel members, disconnected graphs,
general distributed/follower/thermal/moving member loads, direct displacement
control through this unified entry point, production-scale conditioning, both
independent Level 2 comparisons, design-code authority, and release promotion
remain separate gates.
