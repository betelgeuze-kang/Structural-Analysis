# Bounded Frame3D direct displacement control

`stateful_corotational_frame3d_sparse_direct_displacement_control.v1` is an
experimental continuation core with a bounded candidate ModelIR/Python API. It controls exactly one free
node-major `[UX, UY, UZ, RX, RY, RZ]` coordinate and solves the proportional
reference-load factor as an additional unknown. It is executable candidate
evidence; the capability registry remains `public=false`. Same-operator
OpenSees comparisons now cover one monotonic axial-yield UX path, one bounded
combined-hardening UX reversal path, and one elastic pure-axis path for each of
RX, RY, and RZ, but they are not
independent direct-control V&V, design authority, or release authority.

## Scaled augmented equations

Let `L` be the model-bound characteristic length, `D_R` the residual row
equilibration, and `D_u` the physical-coordinate column equilibration. The
unknown vector contains equivalent free coordinates followed by `L * lambda`:

```text
q_equivalent = D_u^-1 u_free
x = [q_equivalent, L * lambda]
g(x) = [D_R R(u, lambda), w * (q_control - q_target)]
J(x) = [D_R K D_u, D_R (-F_reference) / L]
       [w e_control^T,                    0]
```

For rotational control, both the target and control error are converted to the
equivalent translation `L * theta`. This keeps every augmented Jacobian entry
in force-per-length units. The scaling hash binds the source model hash, node
coordinates, reference-load vector, free-DOF order, characteristic length, and
equilibration vectors.

## Commit contract

A target creates a checkpoint only when all of these conditions pass:

- dimensionless scaled translational/rotational residual;
- dimensionless scaled translation/rotation Newton increment;
- load-factor increment;
- equivalent control-coordinate error;
- an admissible, strictly merit-decreasing line-search step;
- same-parent material-path admissibility;
- fail-closed exact-condition sparse factorization diagnostics;
- final reassembled equilibrium and control constraint;
- unchanged parent checkpoint and material-state hashes;
- no fallback and no regularization.

The result retains raw translational and rotational residuals and increments,
the scaled values and tolerances, load-factor increment, scaled condition
number, characteristic length, scaling hash, convergence history, and all line
search attempts. When factorization prevents an increment from existing, those
increment and condition fields remain explicitly unavailable (`None`); they are
never synthesized as numeric zero.

The terminal scalar increment, load-factor increment, and condition number
always describe the terminal iteration. If a later factorization fails, an
earlier successful diagnostic remains in history but is not reused as a
terminal scalar. Targets whose increment is nonzero yet already within the
configured absolute-plus-relative control tolerance fail before Newton entry
with `direct_control_target_within_tolerance`; the solver does not create a
zero-update checkpoint with an empty line-search history.

The direct-control Newton-iteration bound cannot exceed the sparse Frame3D
iteration bound carried by the checkpoint's solver-contract hash. A committed
checkpoint records the number of actually applied line-search/Newton updates,
not the terminal gate-evaluation row, so a convergence reached at the sparse
bound remains self-validating instead of acquiring an off-by-one iteration.

Accepted checkpoints use the stateful sparse Frame3D checkpoint schema and
retain the parent hash. A default monotonic path emits a
`stateful-corotational-frame3d-displacement-control-resume-binding.v1` receipt.
That receipt hash-binds the model, Frame3D solver contract, direct-control
contract, control DOF/unit, path direction, accepted target/step, and accepted
checkpoint hash. Running a prefix and resuming with both its checkpoint and
validated binding reproduces the same checkpoint suffix and final binding as
an uninterrupted run.

The opt-in reversal path keeps v1 unchanged and emits
`stateful-corotational-frame3d-displacement-control-resume-binding.v2` instead.
V2 records `path_mode=cyclic_reversal`, the last completed leg direction,
cumulative requested-target and reversal counts, and a rolling accepted-target
chain head. Its API envelope is
`bounded-frame3d-direct-control-checkpoint-artifact.v2`; a v1 receipt under a
cyclic policy or a v2 receipt under a monotonic policy fails closed.

A sparse checkpoint supplied without the direct-control binding remains a
valid equilibrium-state restart, but the result records
`resume_mode=unbound_equilibrium_checkpoint_restart` and
`resume_contract_verified=false`; it is not represented as exact continuation
of the earlier direct-control contract. A changed direct-control config,
control DOF, checkpoint, receipt field/hash, or reversed target direction fails
closed before the resumed solve. Rejected iterations and blocked steps do not
mutate or replace the accepted parent.

The sparse checkpoint has one deterministic unloaded genesis: step zero has no
parent, zero load/displacement, zero converged iterations, and exactly the
material states and residual reproduced by the zero-state assembly. Later steps
must carry a parent hash and a solver-bounded iteration count. Artifact bytes
use the repository canonical JSON serializer; duplicate keys, `NaN`,
`Infinity`, binary64-overflowing values, negative-zero byte aliases, and raw
integer/typed-float hash-domain drift fail with stable candidate API errors.
Both v1 and v2 artifacts must carry the ordered entity-mapping hash, node IDs,
member IDs, and member-material IDs; missing fields are never substituted from
the current adapter. The resume binding has the same raw-to-typed round-trip
gate as the checkpoint body. Every top-level or composite/distributed-fiber
nested bilinear-steel state is also checked against the exact constitutive
invariants `abs(plastic_strain) <= accumulated_plastic_strain`,
`backstress = Hkin * plastic_strain`, and
`dissipated_energy = Fy * accumulated_plastic_strain` within bounded floating
point tolerance. A completely rehashed but unreachable checkpoint therefore
fails with `material_state_admissibility_failed`; the candidate API translates
that into a stable checkpoint material-state admissibility error before resume.
Concrete damage/history/energy, monotonic confined-concrete state, and
bond-slip reversal/degradation invariants are checked through composite and
distributed-fiber nesting. Every checkpoint material state must also replay
idempotently at its own stored displacement even when the caller requests only
config-independent assembly validation. Non-genesis checkpoints require a
nonzero parent hash, and cyclic completed-target counts cannot exceed the
accepted checkpoint step index. A zero-update child remains valid when a changed
load acts only on restrained equations and the material replay, factorization,
final reassembly, and equilibrium gates all pass; this does not relax the
direct-control rule that a target already inside tolerance fails before solve.

All ModelIR numeric values projected into coordinates, section/material
properties, member roll, or reference loads must be exactly representable as
binary64 before SI unit conversion. A source integer that would round during
`float` conversion is rejected at its original ModelIR path.

## Bounded adaptive target cutback

When a requested control target ends only with
`direct_control_maximum_iterations_exceeded` or a pure admissible
`direct_control_line_search_failed`, the path may retry a smaller target from
the latest accepted checkpoint. A retry is forbidden if any line-search trial
was materially or contractually inadmissible. Sparse factorization, terminal
contract, reference-load, material-integration, and checkpoint/binding errors
also remain immediate fail-closed outcomes.

The cutback contract binds its enable flag, ratio, translation and rotation
minimum increments, recursion depth, accepted-substep bound, whole-path solve
attempt bound, and exact retry reason-code allowlist into the direct-control
config hash. Every scheduled cutback records the rejected target/result hash,
requested target, accepted parent coordinate/checkpoint hash, next target,
reason code, and verified parent-state immutability. Accepted cutback substeps
form the ordinary contiguous sparse-checkpoint chain; a requested target is
complete only after that exact target is committed.

The v1 resume receipt remains exact at completed requested-target boundaries.
If a path accepts an intermediate cutback checkpoint and then blocks before its
requested target, the result records
`final_checkpoint_at_requested_target_boundary=false` and
`exact_checkpoint_resume_supported=false`, and emits `resume_binding=null`;
the v1 binding cannot be reused as an exact replay of the incomplete cutback
orchestration budget/history. Depth/minimum-increment exhaustion records the
final rejected result hash with `outcome=bounds_exhausted`. Whole-path attempt
or accepted-substep limits stop before inventing an unexecuted rejection while
retaining every already accepted intermediate checkpoint in the blocked result.

## Bounded reversal path and v2 lineage

Reversal is disabled by default. It requires
`allow_direction_reversal=true`, a positive bounded
`maximum_direction_reversals`, and exact
`BilinearCombinedHardeningSteel` on every member. Equal adjacent targets,
unsupported material families, a reversal-count overflow, or a cumulative
requested-target count beyond `maximum_path_targets` fails before solving.
This is a narrow combined-hardening steel path, not a general cyclic material
interface.

Each authored target fixes its leg sign from the accepted parent to the target.
Every trial, accepted cutback substep, and retry must remain strictly inside
that leg. Reversal count changes only when a completed authored leg changes
direction; failed trials and cutback retries do not create reversals. The
rolling entry binds the previous chain head, cumulative target index, authored
target, leg direction, reversal flag, requested-boundary checkpoint hash,
accepted step hashes, and an invocation-independent cutback-history hash. Thus
an uninterrupted run and a prefix plus exact v2 resume produce the same final
checkpoint, material state, target-chain head, and v2 artifact even when the
resume begins with a reversal.

The artifact and chain use canonical unsigned SHA-256 self-hashes. They detect
inconsistent fields and accidental corruption and support deterministic
internal continuation, but they are not authentication against an actor who
rewrites a complete artifact and recomputes every hash. No signature, trusted
timestamp, independent operator, or external anchor is claimed.

## Bounded ModelIR and candidate API

ModelIR v2 now accepts the exact capability profile
`bounded_frame3d_direct_displacement_control`. The profile is deliberately
fail-closed before solver entry:

- connected 3D graphs only, bounded to 128 nodes, 256 members, and 768 free
  equations;
- `stateful_corotational_timoshenko_frame3d` members with zero offsets and no
  end releases;
- explicit bilinear combined-hardening steel including both elastic and shear
  modulus—no Poisson-ratio or section-property fallback;
- zero prescribed support values with a translation-centered, scale-normalized
  rank-six rigid-body restraint check;
- exactly one direct-control reference-load pattern, with nonzero loads only on
  free equations;
- explicit arithmetic bounds on coordinates, member roll, material/section
  values and reference loads so SI-to-m/kN/MPa conversion cannot underflow or
  overflow after `analysis_ready=true`;
- no combinations, time functions, construction stages, or unsupported-feature
  rows.

`analyze_bounded_frame3d_direct_control_model_ir` emits result v2 and binds the ModelIR content,
semantic and provenance hashes to the adapter, model, control node/DOF, solver
contract and target request. The result exposes all six node kinematics,
restrained-DOF reactions, per-member bilinear material state, convergence/cutback
counts, dimensionally separate translational `kN` and rotational `kN-m`
residuals plus their dimensionless scaled gate, and explicit non-promotion
authority flags. Nested result values are recursively immutable, while
`to_dict()` returns a detached mutable copy.

When the internal path finishes at a requested-target boundary, the result also
emits a canonical JSON checkpoint artifact. Monotonic paths use artifact v1 and
bounded reversal paths use artifact v2. The artifact contains the sparse
checkpoint and matching direct-control resume binding plus ModelIR, adapter,
model, ordered recovery-entity mapping, control-contract and direction/lineage
hashes. Loading it reconstructs only the bounded
bilinear state, validates state/checkpoint/artifact hashes, reassembles the
equilibrium checkpoint, and verifies the direct-control binding before any new
solve. Prefix-plus-artifact suffix replay reproduces the uninterrupted terminal
checkpoint, node results, reactions and material states exactly.
Result validation also rebinds the retained artifact to the result source,
adapter, model, solver and control hashes; recomputes artifact, checkpoint,
resume-binding and material-state integrity; and checks recovered node/material
identities, values and maximum accumulated plastic strain against the checkpoint. A valid
artifact from another request cannot be transplanted into a rehashed result.

The API is a candidate programmatic entry point, not a capability promotion.
`capability_registry_public=false`, `workbench_execution=false`,
`external_vv_level=0`, `formal_verification_level_2=false`, and
`release_eligible=false` are fixed in the result schema.

## Same-operator axial-yield and rotational comparisons

`examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json` drives a
2 m fixed cantilever through N2 UX targets `0.0015`, `0.003`, `0.0045`, and
`0.006 m`, crossing the declared `250 MPa` axial yield boundary. The current
source is replayed against an actual OpenSees 3.7.1 3D six-DOF
`forceBeamColumn`/`Steel01` model. Control displacement, proportional load
factor, base axial reaction, axial stress, plastic strain, backstress,
accumulated plastic strain, and dissipated energy density pass the declared
`1e-10 + 1e-8 * scale` contract. The run has no cutback, fallback, or
regularization and emits an exact terminal checkpoint.

This closes only a same-operator monotonic axial-yield technical slice. It does
not establish independent reproduction or general cyclic/reversal response,
multi-axis/multi-control behavior, general fiber/shear/torsion coupling,
formal Verification Level 2, or release authority.

The same axial fixture also follows UX targets `0.003`, `0.006`, `0.001`,
`-0.004`, and `0.002 m` with the opt-in cyclic policy. The current product is
compared to an actual OpenSees 3.7.1 six-DOF `forceBeamColumn` using the exact
`Hardening` material parameters `EA`, `FyA`, `HisoA`, and `HkinA`. All five
requested coordinates, proportional load factors, and base UX reactions plus
the final plastic strain, backstress, accumulated plastic strain, and
dissipated energy density form 19 bounded metrics. All five OpenSees analyze
codes are zero; the terminal state is approximately
`plastic_strain=-2.718623004345e-4`, `backstress=-0.271862300435 MPa`,
`accumulated_plastic_strain=0.00464432238734`, and
`dissipated_energy_density=1.16108059684 MJ/m3`. This is same-operator internal
supplemental evidence for one material, one axial member, and one authored
reversal history only.

`examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json` drives the
same bounded 2 m cantilever through N2 RX targets `0.0005`, `0.001`, `0.0015`,
and `0.002 rad` using a `1 kN·m` reference moment. The product and an actual
OpenSees 3.7.1 3D `forceBeamColumn` with the same elastic `GJ` compare control
angle, proportional moment-load factor, and base torsional reaction under the
same `1e-10 + 1e-8 * scale` contract. This specifically exercises the
rotational residual/increment scaling, equivalent-translation constraint, and
rad·kN·m recovery path. It has no cutback, fallback, regularization, or plastic
state and emits an exact terminal checkpoint.

`examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json` and
`examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json` repeat the
four rotational targets with pure MY and MZ reference moments. Each compares
control angle, proportional load factor, and same-axis base moment against an
actual OpenSees `forceBeamColumn` with the corresponding elastic `EI`. This
closes the separate RY/RZ rotational scaling rows and exact checkpoint boundary.
It deliberately does not claim coupled MY+MZ reference-load equivalence: the
product and OpenSees corotational formulations show different second-order
torsional coupling in that broader probe, so coupled multi-axis evidence remains
open.

## Explicit boundary

The profile does not support multiple simultaneous control coordinates,
restrained-DOF control, prescribed-support coupling, unrestricted nonmonotonic
histories or material families,
arc-length continuation, fallback, regularization, member offsets/releases,
Workbench execution, independent direct-control 3D comparison, or public/release
promotion. The same-operator OpenSees evidence now includes the bounded
monotonic axial-yield, exact-steel axial reversal, and pure-axis RX/RY/RZ cases above plus an elastic
load-control case; none can
be relabeled as independent or general direct-control V&V. A reference load must
be explicitly present on at least one free equation; otherwise execution fails with
`direct_control_reference_load_missing`.

Solo-developer and internal AI review may close code structure, numerical
invariants, deterministic replay, failure taxonomy, and focused regression
coverage for this bounded profile. Such review is not an independent operator
attestation, legal or redistribution approval, independent V&V, design review,
or formal Verification Level 2 evidence.

Focused verification:

```bash
python -m pytest -q \
  tests/test_bounded_frame3d_direct_control_api.py \
  tests/test_stateful_corotational_frame3d_displacement_control.py \
  tests/test_stateful_corotational_frame3d_sparse.py \
  tests/test_stateful_corotational_frame3d_materials.py
```
