# Unequal outer reinforcement: core foundation, public integration pending

`make_rectangular_stateful_rc_fiber_section` accepts optional per-bar
`top_bar_area_m2` and `bottom_bar_area_m2`. Missing overrides use the existing
`bar_area_m2`; intermediate rows still use that explicitly common area. The
fiber representation and constitutive laws are unchanged. Positive finite input
is required and Boolean areas are rejected. Optional values do not alter the
original default section contract or checkpoint bytes.

Twenty-six section tests pass. New checks compare small-strain resultants and
tangent to the explicit elastic fiber integral, verify nonzero axial/bending
coupling and its sign reversal on swapping reinforcement, reject parent state
reuse across changed sections, check unchanged legacy identities, and verify
intermediate-row semantics and invalid input rejection. Twenty-one existing
physical-identity tests also pass. Ruff and diff checks pass. These are internal
numerical/software contracts, not measured physical validation.

This does **not** yet expose unequal areas through the public model APIs,
ModelIR adapter/schema, design changes, quantity/cost reports or learned feature
profiles. Those interfaces continue their existing accepted field sets. No
measured specimen is reconstructed, and the Zenodo candidate stays unadmitted.

Remaining coordinated implementation:

- Public compiler inputs in nonlinear_fiber_frame.py and nonlinear_frame.py;
  ModelIR schema and bounded_planar_model_ir.py mapping.
- Section changes and actual longitudinal steel sums in fiber_frame_design.py.
- Entity-invariant identity normalization so explicit default overrides do not
  create artificial independence, while top/bottom swaps remain distinct.
- Candidate and control/layout learning feature/context contracts; unequal-area
  distinctions must not be silently fitted using old common-area weights.
- Public model-to-solve-to-quantity/cost verification and Workbench display/input
  review, with source/receipt/checkpoint bindings preserved.

The change is motivated by observed two-D8/two-D16 reinforcement in the public
beam drawing, but does not supply missing cover, constitutive measurements,
channel mapping or shear/bond validation for that experiment.
