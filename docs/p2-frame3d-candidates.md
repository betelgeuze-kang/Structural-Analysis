# P2 3D frame, shear, warping, and imperfection candidates

These components are experimental reference kernels. They establish explicit
kinematic and constitutive contracts for P2; they are not a promoted 3D
nonlinear analysis workflow.

## Corotational 3D frame energy

`energy_corotated_timoshenko_frame3d_fd2.v1` accepts one two-node member in
global 12-DOF order. Current translation defines the chord. Nodal principal
rotation vectors rotate the initial local triad, and their averaged transverse
director defines an orthonormal corotated frame. The seven basic deformations
are axial extension plus three end rotations at each end relative to that
frame.

The basic elastic energy contains axial, Saint-Venant torsion, and two
Timoshenko bending planes. Global force is a five-point derivative of the same
scalar energy; the symmetric tangent is a deterministic second energy
derivative. This numerical derivative profile is deliberately disclosed. It is
useful as an independent reference and is not presented as a production
analytic tangent.

Tests establish:

- zero-state agreement with the 12-DOF Timoshenko stiffness;
- zero energy and force under a finite arbitrary rigid translation/rotation;
- independent energy-gradient agreement at a deformed 3D state; and
- tangent-column agreement with a centered force derivative.

The rotation-vector branch is restricted below `pi`, and the averaged director
must remain nondegenerate. The element itself has no multi-turn history,
plastic section, or warping coupling.

## Bounded global load path

`dense_elastic_corotational_timoshenko_frame3d_load_control.v1` scatters the
energy-derived element force and tangent into one shared six-DOF-per-node
space. The v1 graph is connected and bounded to 16 nodes, 32 unique members,
and 60 free equations. It accepts explicit nodal reference loads, arbitrary
sorted restraint DOFs, member roll angles, and explicit Timoshenko shear areas.

Each strictly increasing load factor is solved by dense Newton iterations with
the same assembled internal force and tangent. Singular or over-conditioned
free tangents, non-finite corrections, principal rotation-branch violations,
and nonconvergence fail closed. There is no line search, regularization, or
fallback. Accepted checkpoints bind the model, solver contract, load factor,
full displacement vector, residual observation, and parent hash. A prefix plus
resume reproduces the uninterrupted terminal checkpoint exactly.

Terminal recovery reports support reactions and each member's global end
forces, basic deformations/forces, lengths, and strain energy. The focused
cantilever and two-element cases match the Timoshenko bending-plus-shear closed
form and enforce free-equation equilibrium. This remains a small dense elastic
verification path: stateful sections, member releases/offsets/distributed
loads, warping coupling, sparse production assembly, multi-turn rotation, and
release authority are open. A separate same-operator OpenSees comparison now
covers one fixed two-element elastic spatial frame; it is not broad or
independently reviewed external 3D validation.

## Bounded OpenSees comparison

The non-promoting external technical receipt executes a two-element cantilever
with combined global transverse forces and torsion in OpenSees 3.7.1 and this
global 3D path. Fifteen nonzero tip-displacement, support-reaction, and first
member end-force quantities pass the declared
`1e-10 + 1e-10 * max(abs(product), abs(reference), 1)` comparison contract.
The largest absolute error is `5.60000054208626e-12`. The same case is replayed
in the read-only-source, network-disabled container runner and participates in
the 55-scalar host/container parity contract.

This is a fixed, small, elastic, same-operator technical comparison. It does
not establish stateful/material 3D behavior, a production sparse path,
multi-turn rotations, independent-operator reproduction, hierarchy promotion,
or signed engineering review. The roadmap's authoritative external 3D
comparison therefore remains open.

## Native sparse stateful axial-material path

`stateful_axial_material_corotational_timoshenko_frame3d_native_coo_csr.v1`
adds a separate experimental nonlinear path without changing the
checksum-bound dense OpenSees comparison implementation. Each member evaluates
the existing objective corotational Timoshenko geometry from one immutable
accepted parent and replaces its elastic axial constitutive term with one of
six exact material contracts: backward-Euler combined-hardening steel,
asymmetric concrete damage, fracture-energy concrete damage, a perfect-bond
parallel steel-concrete section, a confined-concrete compression envelope, or
a two-layer partial-interaction section with one condensed bond-slip mode. The
section and material initial elastic moduli, including each condensed/effective
composite modulus, must agree in declared units.

The correction is not a secant approximation. If `B` and `H` are the exact
gradient and Hessian of current chord extension, the member adds

```text
f_correction = B^T (N_material - N_elastic)
K_correction = B^T (k_material - k_elastic) B
             + (N_material - N_elastic) H
```

to the energy-derived elastic reference. The material algorithmic tangent is
therefore coupled to the current 3D chord geometry from the same committed
parent state. Focused central differences cover the yielded branch.

The confined-concrete adapter binds the monotonic Mander envelope to immutable
current/max-compression checkpoint lineage while retaining its explicit
monotonic-only limitation. The partial-interaction adapter solves
`N_steel - N_concrete + F_connector(s) = 0` for one internal interface-slip
coordinate and applies its exact scalar Schur tangent. Member length and
reference area must match the frame member exactly; all local Newton trials use
one immutable accepted connector state.

## Distributed axial-biaxial fiber correction

`plane_section_axial_biaxial_discrete_fibers.v1` integrates per-fiber
combined-hardening steel, asymmetric/fracture-energy concrete damage, or the
bounded confined-concrete envelope into `[N, My, Mz]`. Its plane-section strain
is

```text
epsilon_f = epsilon_0 + kappa_y * z_f - kappa_z * y_f
```

and the symmetric `3 x 3` tangent is assembled from the same constituent
algorithmic tangents and immutable parent states. A companion 3D member uses
two- or three-point Gauss integration along the member. It adds the nonlinear
fiber response minus the section's initial elastic fiber response to the
objective Timoshenko reference, so elastic shear and torsion remain separate.
The current seven-mode corotational mapping uses disclosed five-point basic
Jacobians and symmetric basic Hessians; it is a deterministic verification
profile, not a production analytic tangent.

Focused checks cover section and member same-parent finite differences,
initial-reference binding, rigid-body objectivity, axial/biaxial yielding,
native COO/CSR parity, reversal, rollback, schema-bound material checkpoints,
and exact prefix/resume. This base fiber member has no connector field;
multiaxial concrete, cyclic confinement, shear/torsion material coupling, and
production-scale 3D evidence also remain open.

## Distributed two-layer partial-composite correction

`corotational_timoshenko_distributed_two_layer_fiber_bond_slip_condensed.v1`
uses two independently stateful axial-biaxial fiber sections and a linear
two-node slip field. At each lengthwise Gauss station,

```text
epsilon_steel    = B q + beta_steel    * (ds/dx)
epsilon_concrete = B q - beta_concrete * (ds/dx)
beta_steel + beta_concrete = 1
```

where the fixed partition preserves the initial axial-rigidity-weighted mean
strain. A cyclic connector point repeated at an explicit spacing supplies the
line traction. The two internal nodal slips solve layer-plus-connector
equilibrium from the same immutable parent; their exact local `2 x 2` tangent is
Schur-condensed into the five frame basic modes. The global mapping uses the
same disclosed five-point basic Jacobians and symmetric Hessians as the base
distributed fiber candidate.

Focused tests establish weak/strong connector stiffness ordering, local and
global same-parent tangent agreement, cyclic reversal/degradation/dissipation,
failed-local-trial parent immutability, native COO/CSR parity, schema validation,
and exact checkpoint prefix/resume. This bounded path still has no general
shear-lag, uplift/contact, connector-group, effective-width, local-buckling,
member-feature, published composite-member V&V, or design authority.

Member `12 x 12` tangents are scattered directly to free-equation COO rows and
coalesced to sorted canonical CSR. The original small-model contract may use
the public-candidate exact SuperLU policy capped at 256 equations. A distinct
larger graph contract is bounded to 128 nodes, 256 unique members, and 768 free
equations and may use the CPU-only blocked exact-condition policy capped at
1536 equations. The latter solves identity columns in deterministic multi-RHS
blocks; it is exact but quadratic diagnostic work, not a production-scale
condition estimator. A graph above 256 free equations is rejected by the
default policy without regularization or fallback; the larger policy must be
selected explicitly.

An actual 44-node/43-member chain with 258 free equations is assembled and
solved through this integrated path. Its tangent has a finite exact 1-norm
condition number of about `1.918e7`, uses nine 32-column inverse-solve blocks,
and converges after one Newton correction without regularization or fallback.
This is a bounded integration test, not a throughput or memory claim.

An independently scattered dense reference checks internal force, residual,
reaction, tangent and trial-state hash parity on bounded cases. Accepted
checkpoints bind the model, solver policy, full displacement, committed
material states, residual and parent hash. Steel, concrete, confined-envelope,
nested perfect-bond composite, condensed single-mode partial interaction, and
distributed two-layer fiber/connector states are schema-bound. Load targets may
reverse; a failed global Newton or local-condensation trial cannot mutate its
accepted parent, and prefix/resume
reproduces the uninterrupted terminal checkpoint exactly. A four-target
partial-interaction reversal path records two connector reversals, stiffness
and strength degradation, nonnegative dissipation, and exact split/resume
identity.

This closes neither the general 3D material nor production-scale sparse claim.
The simple axial adapters still leave bending elastic; the distributed fiber
adapter makes axial and both bending resultants stateful, and the separate
two-layer adapter adds connector/interface quadrature and a condensed linear
slip field while shear and torsion remain elastic. Cyclic confined-concrete laws,
general shear lag/uplift/contact and connector groups,
releases/offsets/member loads, warping coupling, analytic 3D tangents,
production-scale material/conditioning/performance evidence, independent
external review and release authority remain open.

## Shear-deformable beam

`two_node_timoshenko_frame3d_shear_condensed.v1` provides a local symmetric
12-DOF prismatic stiffness with explicit effective shear areas in local `y` and
`z`. It never infers a shear correction factor or effective area. A one-element
cantilever reproduces

```text
delta = P L^3 / (3 E I) + P L / (G As)
```

and converges to the existing Euler-Bernoulli matrix as both effective shear
areas tend to infinity.

## Torsion and warping

`vlasov_hermite_twist_gradient_2node.v1` is a separate four-DOF kernel with end
twist and twist-gradient DOFs. Cubic Hermite interpolation integrates

```text
U = 1/2 integral [GJ (theta')^2 + E Cw (theta'')^2] dx.
```

It exposes twist moments/bimoments and the exact linear tangent. With `Cw=0`,
static condensation of the two gradient DOFs recovers the Saint-Venant
`GJ/L [[1,-1],[-1,1]]` matrix. It is not silently inserted into the existing
12-DOF frame because that frame has no warping DOF or open-section stress
recovery.

## Explicit initial imperfection

`sinusoidal_member_bow_local_yz.v1` subdivides one explicitly oriented member
and adds a half-sine bow in its rolled local `y/z` directions. End coordinates
remain exact, the combined amplitude is bounded to `L/20`, and the full nominal
and imperfect coordinate sets are canonical-hashed. The function does not
choose a code amplitude, eigenmode, residual stress, or imperfection sign for
the engineer.

## Verification

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_p2_frame3d_candidates.py \
  tests/test_corotational_frame3d_global.py \
  tests/test_stateful_corotational_frame3d_sparse.py \
  tests/test_stateful_corotational_frame3d_materials.py \
  tests/test_stateful_biaxial_fiber_section.py \
  tests/test_stateful_corotational_fiber_frame3d.py \
  tests/test_stateful_corotational_partial_composite_frame3d.py \
  tests/test_corotational_frame3d_scalable_graph.py \
  tests/test_scalable_sparse_factorization.py
```

These tests are local analytic, invariance, dense/sparse assembly, equilibrium,
same-parent steel/concrete/confined/perfect-bond/single-mode and distributed
partial-interaction constitutive tangent, material commit/rollback, cyclic connector and load-target
reversal, 258-equation sparse integration, and replay evidence. A bounded
same-operator OpenSees technical comparison also passes, but authoritative
independent external 3D validation, published material/member cyclic
validation, general shear-lag/uplift/contact and connector-group behavior,
production sparse/material performance evidence, and signed engineering review remain
open.
