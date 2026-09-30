# Unequal outer reinforcement: public inputs, quantities and guarded learning

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

## Public integration

The canonical public RC and corotational compilers now accept the two optional
area overrides and pass them to actual section fibers. Explicit null, Boolean,
nonpositive and nonnumeric values are rejected at the public boundary. The
bounded planar ModelIR adapter forwards the fields; Python and mirrored native
ModelIR schemas allow positive numbers only. This schema update does not claim
native runtime execution of this RC formulation.

`FiberFrameSectionChange` can set either override. Omission leaves the existing
section value in place. Changing the common area changes default outer bars and
intermediate bars; it does not overwrite explicitly authored outer overrides.
Candidate serialization omits the new fields when unset, preserving legacy
experiment identities. A changed section still requires actual reanalysis.

Member quantities use top count times top area, bottom count times bottom area,
and intermediate count times common area. Existing common-area arithmetic stays
exact when overrides are omitted or equal to the common value. Price estimates
continue to use that quantity at the same declared price table, with existing
scope exclusions and no confirmed construction-cost savings claim.

Physical duplicate detection discards redundant default overrides but retains
nondefault outer areas. Swapping top and bottom remains distinguishable even
when total steel volume is unchanged. Existing candidate feature names and
weights are not reinterpreted: aggregate steel volume is corrected, while outer
area overrides remain in the **fixed analysis context**, including control/layout
contexts. Previously fitted common-area policies reject a changed context.

This is deliberately not a learned feature profile for freely varying top and
bottom areas. A versioned descriptor/training experiment is still required for
ranking those changes across contexts. Workbench input/display review also
remains open. No measured specimen is reconstructed and the Zenodo candidate
stays unadmitted.

The change is motivated by observed two-D8/two-D16 reinforcement in the public
beam drawing, but does not supply missing cover, constitutive measurements,
channel mapping or shear/bond validation for that experiment.

## Verification of the public integration

Final local focused/regression selection: **377 passed in 139.55 s** across
13 files: section core, public RC API, section changes/quantities/costs, physical
identity, candidate learning, bounded ModelIR, ModelIR contract, layout features,
direct-control design/search, candidate search/suite and workflow contract.
Ruff and `git diff --check` passed. Public unequal-area models complete the
requested path and result validation; an unequal-area design candidate passes
fresh full-reference verification and uses actual bar mass with a common
synthetic price table. This is not measured specimen or real-price evidence.

The first regression run exposed a new test's incorrect validation-report field
name and a synthetic candidate-suite fixture using generic dataclass serialization.
Both were corrected; the final complete selection above passes. Production
candidate bindings and fixtures use the explicit backward-compatible serializer.

The independent development CI lane now selects 58 files, including these
regressions; full-suite preparation and acceptance requirements remain intact.
Hosted results for the new source are pending, distinct from the prior published
1d8f4e7a5 receipt.

[Workbench review integration](rc-unequal-reinforcement-workbench-20260920.md)
now verifies separate outer-area quantities and labels in both comparison
surfaces. The original pending UI review item above is superseded for report
import/display; interactive editing and cross-area learning are still open.
