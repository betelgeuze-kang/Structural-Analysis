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
