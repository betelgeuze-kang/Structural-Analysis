# Phase 2 state-updated bilinear link Newton seed

This slice adds a native force-deformation link material. It does not represent
the link as an artificial stress-strain continuum.

## Implemented contract

- translational 1D force in kN and deformation in m;
- backward-Euler bilinear return mapping with linear isotropic and kinematic
  hardening;
- immutable plastic deformation, backforce, accumulated plastic deformation,
  and dissipated-energy state;
- deterministic little-endian checkpoint hashes;
- cyclic reversal and nonnegative energy-dissipation checks;
- same-parent algorithmic tangent finite differences;
- explicit force-deformation assembly mode alongside the existing
  stress-strain element mode;
- one-link force/tangent assembly and a two-link displacement-controlled
  Newton path with deterministic replay, exact rollback, residual/increment
  gates, line-search history, zero fallback, and zero regularization.

The canonical receipts are:

- `implementation/phase1/release_evidence/productization/phase2_state_updated_bilinear_link_result.json`
- `implementation/phase1/release_evidence/productization/phase2_state_updated_bilinear_link_summary.json`

Regenerate or verify them with:

```bash
PYTHONPATH=src python scripts/build_phase2_state_updated_bilinear_link_artifacts.py
PYTHONPATH=src python scripts/build_phase2_state_updated_bilinear_link_artifacts.py --check
```

## Claim boundary

This receipt remains one bilinear translational link family only. A separate
bounded compression-only gap contract described below does not change this
receipt or promote general link-family closure. Friction, impact, restitution,
local/follower contact normals, general foundation uplift, viscous and
viscoelastic devices, multi-DOF coupling, rate dependence,
degradation/pinching, shell connection integration, and published or
experimental validation remain open. A separate bounded
[linked-frame cyclic benchmark](stateful-corotational-linked-frame-cyclic-benchmark.md)
now scatters this scalar global-axis link into two active corotational frame
DOFs and commits the frame and link states atomically. A second bounded
[fixed-reference local-axis benchmark](stateful-corotational-local-axis-linked-frame-cyclic-benchmark.md)
projects one scalar link through a four-DOF direction-cosine row derived from
the undeformed endpoints. A third bounded
[updated-current-axis benchmark](stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.md)
uses current length minus reference length, rotates the internal force with the
current chord, and adds the consistent force-times-length-Hessian geometric
tangent. A fourth bounded
[scalar rotational-link benchmark](stateful-corotational-rotational-linked-frame-cyclic-benchmark.md)
uses a separate moment-rotation material and immutable rotational state to
couple two free `rz` DOFs; it does not reinterpret the translational receipt's
kN-m force-deformation fields. A fifth bounded
[compression-only gap benchmark](stateful-corotational-gap-linked-frame-cyclic-benchmark.md)
uses a separate open/closed active-set state and one global-x frictionless
elastic gap; it does not establish general contact or uplift capability. These
results do not establish general nonconservative follower external loads,
coupled multi-axis response, shell integration, or general link-family breadth.
Full-building G1 and production ROCm/HIP material parity also remain open.

The receipt keeps `link_spring_material_breadth_closure_claim=false`,
`material_newton_breadth_closure_claim=false`,
`g1_material_newton_breadth_claim=false`, and
`production_nonlinear_closure_claim=false`.
