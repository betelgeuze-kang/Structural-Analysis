# P2 3D frame reference kernels

This slice provides four bounded experimental reference kernels. It does not
promote a general 3D nonlinear workflow, verification Level 2 or 3, design
authority, or release readiness.

## Explicit-shear Timoshenko frame

`two_node_timoshenko_frame3d_shear_condensed.v1` returns a symmetric local
12-DOF prismatic stiffness. Effective shear areas in both transverse
directions are mandatory inputs; the implementation does not infer a shear
factor. A one-element cantilever matches bending plus shear closed form and
the large-shear-area limit matches the existing Euler-Bernoulli kernel.

The kernel has no locking study, nonlinear section state, global assembly, or
external validation.

## Energy-based corotational frame

`energy_corotated_timoshenko_frame3d_fd2.v1` accepts one two-node member in
global 12-DOF order. The current chord and the averaged rotated transverse
director define the corotated frame. Seven basic deformations cover axial
extension plus three relative end rotations at each end.

Force is a five-point derivative of one scalar elastic energy. The symmetric
tangent is a deterministic second energy derivative. This is a disclosed
numerical reference profile, not a production analytic tangent. Principal
rotation vectors are restricted below `pi`; multi-turn history, stateful
materials, releases, offsets, distributed loads, warping coupling, global
nonlinear assembly, and external V&V remain open.

## Torsion and warping

`vlasov_hermite_twist_gradient_2node.v1` is a separate four-DOF linear
Vlasov kernel with twist and twist-gradient end coordinates. It integrates
Saint-Venant torsion and warping energy with cubic Hermite interpolation.
With zero warping constant, condensation of the gradient coordinates recovers
the two-DOF Saint-Venant stiffness.

The kernel is intentionally not inserted into the 12-DOF frame because that
frame has no warping coordinate or open-section stress recovery.

## Explicit initial imperfection

`sinusoidal_member_bow_local_yz.v1` subdivides one explicitly oriented member
and applies a half-sine bow in rolled local y/z directions. End coordinates
remain exact, the combined amplitude is capped at `L/20`, and nominal and
imperfect coordinates are canonical-hashed.

The generator does not choose a code amplitude, eigenmode, residual stress,
imperfection sign, or solver path.

## Focused verification

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_p2_frame3d_candidates.py
```

The tests cover the bending-plus-shear closed form, Euler-Bernoulli limit,
Saint-Venant condensation, rigid twist, deterministic imperfection geometry,
finite rigid-motion objectivity, energy-gradient agreement, and tangent-column
agreement. These are local analytic and invariance checks only.
