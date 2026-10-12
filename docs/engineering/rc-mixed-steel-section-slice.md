# Mixed steel constituents in the stateful RC section

Public beam datasets can distinguish top hanger bars from tension reinforcement
by both area and coupon properties. The current rectangular public input accepts
one shared steel material and bar area. Adding intermediate positions alone does
not represent those specimens faithfully.

This slice adds immutable `steel_overrides` pairs `(fiber_id, steel_material)` to
`StatefulRCFiberSection`. Existing fibers already carry their own area and position.
Only existing steel fibers can be assigned; unknown/concrete/duplicate references,
mutable containers, and unsupported material types are rejected. Assignments are
canonicalized in fiber order. Default fibers retain `section.steel`.

Each assigned law drives initial state and constitutive integration. Section
identity includes nonempty assignments, including every material parameter;
changing a law invalidates prior section/frame checkpoints. Omitting assignments
preserves the exact legacy section hash. Material-state projection and terminal
recovery label each constituent with its actual assigned material identifier.

Verification covers unequal-area elastic stiffness, separate yielding, reversed
nonlinear histories, tangent differences, dissipation, immutable parent states,
Newton failure rollback, persisted frame checkpoints, and material identity through
the full engineering recovery path. The original 150 kN L-frame loading schedule
is retained for two authored material cases: a 100 MPa top-steel case reaches
0.75 but fails at 1.0 with exact rollback and cannot create a completed checkpoint
chain; a distinct 404 MPa case completes and replays exact fiber stresses. The
100 MPa failure is a bounded solver observation, not a physical capacity claim.
Neither case is an Alberta specimen simulation or a fitted material model.

This is the constitutive foundation for explicit mixed reinforcement, not its
public input or product completion. Follow-up work must carry explicit layers,
positions, areas and material references through public compilation, quantities,
durable requests, artifact identity and Workbench reports. The existing draft
intermediate-layer slice uses a common steel area/material and cannot alone close
that requirement. Public-source force/datum correspondence, complete constitutive
inputs, shear/bond scope and physical tolerances remain separate open requirements.
