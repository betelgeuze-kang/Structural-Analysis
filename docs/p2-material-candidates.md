# P2 material candidates: confinement, bond slip, and partial interaction

These contracts move three previously research-only concepts into the
`structural_analysis.materials` package. They remain experimental and carry no
public or design authority. The confined-concrete envelope and a bounded
single-slip-mode partial-interaction adapter are wired into the experimental
native-sparse 3D member path. A separate two-layer fiber member now adds
connector quadrature and a condensed linear slip field; neither path is a
general shear-lag, uplift/contact, effective-width, or design-code formulation.

## Confined concrete

`ConfinedConcreteMaterial` implements the bounded monotonic uniaxial Mander
compression envelope using explicit unconfined strength, elastic modulus,
unconfined peak strain, and effective lateral pressure. The peak strength and
strain increase with confinement, the analytic tangent is checked against a
same-point central difference, and tension is explicitly open.

The model does not claim multiaxial validity, cyclic pinching, localization,
bar buckling, bond coupling, published calibration, or code compliance.

`ConfinedConcreteState` adds immutable current/max-compression lineage so a 3D
member checkpoint can replay the envelope exactly. It does not add an unloading
law: the constitutive response is still the disclosed monotonic envelope.

## Bond-slip connector

`BondSlipMaterial` uses SI units and an elastic–softening–residual envelope.
`BondSlipState` is immutable and carries a canonical state hash, reversal
count, stiffness and strength degradation, and accumulated nonnegative
dissipation. Cyclic unloading/reloading is evaluated from the caller-owned
committed state; trial evaluation never mutates that parent.

This is one local connector point. Distributed anchorage, reinforcing-bar
development, interface quadrature, and published cyclic calibration remain
outside the profile.

## Partial composite interaction

`PartialCompositeMaterial` keeps steel axial rigidity, concrete axial rigidity,
and connector slip as three explicit generalized coordinates. It returns
constituent axial forces, connector force, the block-diagonal consistent
tangent, interaction ratio, and the exact connector state lineage.

The candidate is not a composite beam, shear-lag, uplift/contact, or member
failure formulation. It cannot be used as design authority.

## Condensed axial member coupling

`CondensedPartialCompositeAxialMaterial` supplies one bounded bridge from the
material point to a frame member. For total member strain `epsilon` and internal
slip `s`, it uses

```text
epsilon_steel    = epsilon + s / L
epsilon_concrete = epsilon - s / L
g(s) = N_steel - N_concrete + F_connector(s) = 0.
```

The local scalar equilibrium is solved from the immutable accepted connector
state. The exact Schur derivative of `g` produces the condensed member tangent;
trial evaluations do not mutate the accepted parent. Member length and reference
area are checksum-bound and must exactly match the 3D member. Focused tests cover
same-parent finite-difference tangent agreement, native COO/CSR parity, cyclic
connector degradation, failed-trial parent immutability, and exact checkpoint
resume.

This adapter is only one internal slip mode per axial member. It has no
connector field, interface quadrature, composite bending, shear lag,
uplift/contact, distributed fiber section, or published calibration. The
separate distributed member below addresses only the first three of those
mechanics within a bounded two-layer kinematic profile.

## Axial-biaxial fiber section

`StatefulBiaxialFiberSection` is a separate distributed-member building block.
It integrates explicit `(y, z, area, material)` fibers into `N`, `My`, and `Mz`
with the exact same-parent `3 x 3` tangent. Supported fiber laws are
combined-hardening steel, asymmetric or fracture-energy concrete damage, and
the bounded confined-concrete envelope. A 3D corotational member evaluates this
section at two or three lengthwise Gauss points; see
[P2 3D frame candidates](p2-frame3d-candidates.md).

The section by itself does not add connector kinematics, multiaxial concrete,
or shear/torsion material coupling.

## Distributed partial-composite member

`StatefulCorotationalPartialCompositeFrame3D` couples two independently stateful
axial-biaxial fiber sections to a linear two-node interface-slip field. At each
of two or three lengthwise Gauss stations it evaluates a cyclic `BondSlipMaterial`
as a connector repeated at an explicit spacing. The two slip coordinates solve
the variational layer/connector equilibrium from one immutable accepted parent.
The exact local `2 x 2` tangent is statically condensed into the five selected
corotational frame modes. Connector reversal, degradation, section damage/yield,
local residual, native COO/CSR assembly, and the full state are checkpointed.

This is a bounded two-layer formulation with zero natural end-slip traction and
an initial-axial-rigidity-weighted mean-strain partition. It does not infer slab
effective width, connector layout, anchorage, uplift/contact, local buckling,
general shear lag, or design resistance. Published composite-member validation,
production-scale evidence, and external review remain open.

Focused verification:

```bash
PYTHONPATH=src python -m pytest -q tests/test_p2_material_candidates.py
PYTHONPATH=src python -m pytest -q \
  tests/test_stateful_corotational_frame3d_materials.py \
  tests/test_stateful_biaxial_fiber_section.py \
  tests/test_stateful_corotational_fiber_frame3d.py \
  tests/test_stateful_corotational_partial_composite_frame3d.py
```
