# Independent outer longitudinal steel centroid distances

The source reconciliation for [Tan and Nguyen 2019](tan-2019-source-reconciliation-20260920.md)
exposed a representational restriction: unequal outer steel areas were supported,
but both layers shared one face-to-centroid distance. This change adds optional
`top_cover_m` and `bottom_cover_m` to the existing rectangular RC section factory,
both public compilers, ModelIR adapter and mirrored Python/native JSON schemas,
and canonical section-change candidates.

All three cover fields mean **concrete face to longitudinal steel centroid**, in
metres, not clear cover to a stirrup or bar surface. Each optional field defaults
to `cover_m`. Each distance must be finite, positive and below half the depth;
the required common distance is validated even when both overrides are supplied.
Explicit JSON null, boolean and string values are rejected. Intermediate layers
must lie strictly between the actual outer positions. This does not implement
arbitrary reinforcement positions across the section centre or distinct steel
constitutive laws for different layers.

Default sections and omitted candidate fields retain their previous identities.
Physical duplicate detection canonicalizes effective positions, including redundant
shared-distance aliases, while retaining actual position differences. Asymmetric
placement changes the fixed context of existing symmetric candidate policies;
no existing feature vector or trained weights are relabelled. No policy is trained
or promoted by this implementation.

The comparison path applies changes to a detached canonical model and executes
full reference reanalysis. Moving otherwise identical straight longitudinal bars
does not change the current quantity/cost scope. Workbench validators accept the
new fields, validate their bounds, and show explicitly authored face-to-centroid
distances without implying clear-cover compliance.

## Focused verification

- 200 Python checks passed across section integration, both public input paths,
  physical identity, design comparison, candidate learning and reinforcement policy
  modules. Checks include elastic fibre integration/coupling, parent-state rejection,
  legacy identities, invalid input, full public solve/result validation and candidate
  reanalysis with unchanged quantities/common prices.
- TypeScript type checking passed.
- 35 existing/new unequal-steel Workbench checks passed, including desktop/mobile
  legacy result rendering, new distance validation and intermediate-layer bounds.
- Ruff and `git diff --check` passed for the changed implementation and tests.

These are software and internal solver checks, not independent experimental
validation. The Tan/Nguyen input conflicts, incomplete source histories and paper
licensing remain unresolved; no specimen was admitted to training or reconstructed
as a qualified physical benchmark. No AI speedup, construction saving or release
qualification is claimed.

## Original result delivery

The exclusive-output fixture builder ran against committed solver source
`b6b4507a526c3df1b07abb3dc7392c14282234bd`. Its baseline and asymmetric candidate
both passed fresh full reference verification; the original report contains
31,872 bytes, stored as a 6,752-byte deterministic gzip fixture. Decompressed
SHA-256: `d145dc0d3bf4f61fd8cb1b69c174f841c6e97d2fa623e60b6f2bd450ce74ae6b`.
This is synthetic internal evidence, not a reconstruction of an external beam.

An additional 88 Workbench checks passed for original report validation,
comparison delivery and existing reinforcement search. Desktop/mobile browser
checks load the asymmetric fixture and display its actual centroid distances.
The first-column section description now wraps within 16 rem so the new geometry
is readable at a 390-pixel viewport while numeric comparison columns remain in
the existing horizontal table.

After the wrapping adjustment, 37 centroid/unequal-steel browser checks passed
and TypeScript checking passed again. The 390-pixel screenshot was inspected:
both reinforcement areas and the 0.04/0.06 m face-to-centroid distances are readable.
The total distinct frontend checks across this focused validation are 123;
repeated checks are not counted as new cases.
