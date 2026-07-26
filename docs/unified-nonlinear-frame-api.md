# Unified Nonlinear Frame API

`analyze_nonlinear_frame` and `structural-analysis-nonlinear-frame` select one
explicit analysis profile while returning the same typed envelope and SI field names.

| Profile | Current boundary |
| --- | --- |
| `fixed_chord_serial_cantilever.v1` | Existing bounded serial-cantilever Developer Preview |
| `corotational_one_bay_portal.v1` | Four-node, three-member rectangular portal candidate |
| `corotational_connected_frame2d.v1` | Connected branching 2D frame candidate with multiple supports, proportional prescribed displacement, and bounded member features |

The portal compiler requires two fully fixed bases, proportional nodal and/or bounded
member loads, explicit rectangular RC fiber sections, and supported steel/concrete laws.
Unsupported keys, topology, support, load, material, section, unit, or coordinate
semantics fail before solve.

The connected-frame compiler accepts 2-128 unique planar nodes and 1-256 unique
two-node members in one connected graph. Any number of support nodes may restrain a
non-empty subset of `UX`, `UY`, and `RZ`. A support may add
`prescribed_values`, whose translation values are metres and rotation values are
radians at full load; intermediate targets use `u_prescribed(lambda)=lambda*u_full`.
The prescribed coordinates are written into every trial assembly and checkpoint, and
their constrained residuals remain reaction truth. A prescribed-only, fully constrained
case follows the explicit reaction-only/no-Newton contract.

Both corotational profiles support proportional load control (the default) and direct
single-DOF displacement control. Direct control replaces one free generalized coordinate
with the solved load factor, imposes the requested `UX`, `UY`, or `RZ` target exactly,
and enforces equilibrium on every free equation with an analytic load-factor residual
derivative. Dense and native-CSR augmented systems share the same checkpoint, J1-J5,
engineering-recovery, and exact restart contracts. This is direct control only; arc-length,
multi-point, adaptive target selection, and dynamic control are outside this profile.

Both corotational profiles accept three optional fields on a member:

- `end_releases`: exact `i` and `j` lists containing at most `RZ`;
- `rigid_offsets_global_m`: exact `i` and `j` global XY vectors in metres;
- `uniform_distributed_load_local`: a uniform `qx_kN_per_m`/`qy_kN_per_m`
  dead load with `basis=initial_member_local` and `behavior=dead`.

Rigid offsets use the finite-rotation rigid-arm map and its exact second derivative.
Released rotations are internal coordinates whose end-moment equilibrium is solved at
every trial, then eliminated from the analysis tangent. The member load uses the
consistent Euler-Bernoulli element vector and participates in release equilibrium.
Unsupported release components, follower or partial-span loads, and alternate load
bases fail before solution. See `docs/corotational-member-features.md`.

For a ready corotational result, the API binds:

1. the canonical model checksum and portal compiler hash;
2. J1-J5 topology, scaling, state ancestry, solver-state, and convergence receipts;
3. exact terminal-parent engineering replay and immutable SI artifacts;
4. a complete epoch-zero-rooted checkpoint-chain hash and canonical artifact bytes;
5. normalized displacement, reaction, member, section, and fiber rows.

When a restart artifact is supplied, every prefix step is solved again from genesis and
its checkpoint bytes must match before any remaining step runs. A valid terminal chain
therefore replays to identical engineering output; altered bytes, model identity, load
prefix, parent link, state hash, or non-canonical JSON fail closed.

The command line writes result/report/checkpoint files atomically:

```bash
structural-analysis-nonlinear-frame \
  examples/public_corotational_rc_portal.json \
  --profile corotational_one_bay_portal.v1 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out result.json \
  --report-out report.json \
  --checkpoint-out checkpoint-chain.json
```

Direct displacement-control example:

```bash
structural-analysis-nonlinear-frame \
  examples/public_corotational_member_features.json \
  --profile corotational_connected_frame2d.v1 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --control-mode displacement_control \
  --control-node N2 \
  --control-dof UY \
  --terminal-control-displacement -0.00016 \
  --out displacement-result.json \
  --report-out displacement-report.json \
  --checkpoint-out displacement-checkpoint-chain.json
```

The corotational profile accepts `numpy_linalg_solve_dense` or
`scipy_sparse_spsolve_cpu`. The sparse path scatters element tangent entries directly
to COO and canonical sorted CSR; it does not materialize a dense global tangent before
factorization. Runtime metrics disclose both backend selection and whether native sparse
assembly was observed. Dense/sparse parity is bounded by focused assembly and full-path
SI result tests. Every sparse factorization is governed by the hashed
`public_sparse_factorization_fail_closed.v1` policy; the result exposes diagnostic
hashes plus aggregate condition, pivot, and backward-error extrema.

The corotational endpoint is a Developer Preview **candidate**, not a release or design
claim. Large-scale sparse policy, both Level 2 comparisons, broader member-load and
release families, and design-code authority remain separate gates. The Workbench may
consume this result but cannot redefine its authority.
