# Selected RC model discretization in Workbench

The RC design review now displays concrete layers through each section's depth
and integration points along each member. Values come from the selected
candidate's already verified original canonical model, beside its geometry and
original artifact identities. Selecting a different candidate updates the model
binding. The UI does not infer defaults, change the model, rerun analysis or
represent the counts as a numerical convergence certificate.

This addresses a concrete omission exposed by the planar refinement studies:
solver settings alone do not describe section quadrature. The existing selected
model showed width, depth, cover and reinforcement but omitted these two counts.
The display change belongs to the experimental RC design/search review; it does
not add a new public planar solver profile or extend any numerical layer limit.

## Verification

The production build, TypeScript check and viewer-delivery contract pass, with
the existing large-bundle warning. Seventeen browser tests pass in 1.0 minute:
the design-review suite plus four actual HTTP search-review tests. Assertions
compare displayed section/member counts directly with the selected fixture's
original model at desktop 1440 px and mobile 390 px. They retain candidate
selection, exact-byte downloads, failed/changed artifact handling, tenant and
credential rejection and method restrictions.

The actual HTTP desktop/mobile selection tests were repeated after adding
focused screenshots (2 passed in 24.8 s); those are repeated coverage, not two
additional independent scenarios. The HTTP tests do not intercept browser
responses. The separate design-review tests use route fulfillment with original
fixture bytes. No numerical solve, fit or production service validation occurred.

The focused mobile image was visually inspected: both labels and integer values
are readable and wrap within the panel. Automated overflow checks pass at both
widths. The temporary preview process started for this change was stopped after
verification. Existing result files and their hashes were not modified.

## Retained evidence

The packet includes source patch, both focused screenshots, both actual HTTP
transport receipts and a validation summary:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-discretization-workbench-7rppgj07`

Six payload files, 130,258 bytes; inventory SHA-256:
`15e2f332fe3c591a28a54f3a7d5eb475f24595b9fdbe393f908b85a182fe0ce2`.

The earlier passing nodal/steel refinement screen and nonpassing concrete cell
projection remain separate numerical observations. Showing these model settings
helps users distinguish observations; it does not resolve physical verification,
independent data rights, learned net savings or full roadmap acceptance.
