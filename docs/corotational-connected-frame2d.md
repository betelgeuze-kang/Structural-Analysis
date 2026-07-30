# Connected Corotational Frame2D Candidate

`corotational_connected_frame2d.v1` extends the bounded corotational frame
pipeline from the rectangular portal to a connected planar graph. It remains an
experimental, non-promoted candidate.

The v1 compiler accepts 2–128 unique XY nodes and 1–256 two-node members. The
graph must be connected and may branch, but parallel members between the same
node pair are rejected. Each support row may constrain a non-empty unique subset
of `UX`, `UY`, and `RZ`; one or more support nodes are required.

Support rows may include `prescribed_values` for constrained components. Those
terminal values are scaled by every load factor, included in the problem hash,
checked byte-for-byte in committed checkpoints, and replayed through dense or
native sparse assembly. A fully constrained prescribed-only model uses the
reaction-only no-solve disposition: it commits exact checkpoints and reactions
without executing Newton or making a convergence claim.

If prescribed motion is the only excitation and free equations remain, the
profile fails before Newton with
`corotational_equation_scaling_unavailable` at
`/solver/equation_scaling`. It does not turn a missing force reference into a
numeric default. A source-bound kinematic reference-force contract is required
before that iterative path can be supported.

For a ready result, the compiler and adapter bind connected topology, exact
six-DOF ordering, solver-coordinate and physical-equation scaling, proportional
nodal loads and prescribed values, member-feature hashes, checkpoint ancestry,
solver/assembly identity, no-fallback execution, a terminal dimensionless
free-equation residual trace, the full-load terminal contract, exact engineering
recovery, a typed engineering ResultIR manifest, and canonical checkpoint-chain
replay. The manifest grants exact bounded candidate recovery authority to the
registered finite rigid offset, RZ release, and initial-local uniform member-load
features only. The profile-specific adapter hash is not a claim that
the `engine_v2_phase0_linear_3d` ModelIR profile represents nonlinear RC fiber
state. The separate ModelIR v2 `bounded_planar_frame_alpha` branch now represents
this exact bounded input and binds its content/semantic/provenance hashes through
`analyze_nonlinear_frame_model_ir` into the nonlinear topology and unified result.
The topology remains a nonlinear candidate contract, not linear-static Engine v2
`ExecutionPlan v1`.

The cross-platform determinism workflow replays both the member-feature fixture
and `examples/bounded_planar_settlement.model-ir.v2.json` on Ubuntu and Windows
with Python 3.10 and 3.12. Each coordinate receipt freezes the fixture bytes,
source/semantic/provenance identities, adapter and execution-plan bindings,
result, checkpoint chain, physical-equation scaling, residual trace, and exact
engineering-recovery hashes. The four-way aggregate fails closed when either
case is absent or rehashed after modification. This is only an authored gate
until one clean, retained current-source GitHub Actions matrix receipt passes;
it does not by itself establish cross-platform evidence or release authority.
For current-main runs, the aggregate receipt is also attested and immediately
verified against the exact source digest, main ref, hosted-runner policy, and
`engine-v2-determinism-ci.yml` signer identity. Pull-request runs retain the
same four-way numerical gate but do not mint a provenance attestation.

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_branching_frame.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 4 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out connected-result.json \
  --report-out connected-report.json \
  --checkpoint-out connected-checkpoint-chain.json
```

The lower-level assembly package also exposes a bounded dense direct
displacement-control candidate with augmented consistent Newton, proportional
support-motion coupling, exact rollback, and accepted-checkpoint restart. That
internal solver is documented separately and is not wired into this unified
J1–J5 profile.

Finite rigid offsets, RZ end releases, and uniform member dead loads in initial
local axes are exposed by this unified profile and remain separately registered
bounded candidates with exact bounded engineering-recovery authority. They do
not create authority for any other member-feature family. The
lower-level direct displacement-control solver remains outside the unified
entry point. Disconnected graphs, parallel members, general
distributed/follower/thermal/moving member loading, production-scale
conditioning, independent Level 2 comparison evidence, design authority, and
release promotion remain outside this slice.
