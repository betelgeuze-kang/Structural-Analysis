# Declared campaign aliases across public archives

The [public-source review](public-source-lineage-review-20260913.md) identifies
ACI/PEER/NIST lineage as a potential source of split leakage. Exact response
matching already rejects identical curves and ordered excerpts, but cannot link
different specimens or rounded/processed curves from one campaign under different
archive labels. This change accepts an explicit reviewed declaration of those
campaign aliases; it does not infer source lineage or authenticate a declaration.

`decode_measured_response_workbook` accepts optional `campaign_aliases`, an
immutable tuple of at most 32 distinct bounded identifiers, excluding the primary
campaign ID. The frozen response object validates these constraints, including
when constructed directly or replaced. Aliases follow the existing campaign-ID
syntax; a DOI or URL is provenance to review, not automatically a campaign ID.
No global repository name should be used to merge unrelated campaigns.

The existing real learning preflight places primary IDs and aliases in the same
ownership namespace. A record joining two names must not connect training and
validation/holdout, regardless of input order. Rejections retain the exact matched
campaign identifier, the previous split, elapsed source-screen time and zero
structural calls/fits. Same-split reuse remains allowed. Sorted aliases appear in
the source identity and hence the study plan; source bytes and SI observation
identities are unchanged. With no aliases, the former identity fields are
unchanged. Independent-provenance and training-admission flags remain false.

Focused workbook/split checks pass **63 tests in 1.79 s**. New cases include
different curves with a declared common origin, both record orders, all six
orders of a three-record alias bridge, invalid declarations, retained observation
identity and an actual learning-entry rejection before compilation, solve, fit or
output creation. These are authored metadata/response fixtures, not an acquired
external corpus. Ruff and the two-source-file mypy checks pass.
The separate actual learning/geometry-history split regression passes **55 tests
in 132.19 s**, retaining the existing train-only fit and evaluation behavior.
Together these are 118 selected passing tests, not a full repository run.

## Existing A1 candidate: classification is not material-model correspondence

The publisher's [1994 article abstract](https://www.concrete.org/publications/internationalconcreteabstractsportal.aspx?id=4181&m=details)
describes a high-strength concrete column campaign varying transverse
reinforcement and axial stress, with confinement and longitudinal-bar buckling
among the subjects. The [PEER A1 record](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=201)
reports flexural failure and 102.7 MPa concrete strength. The primary publication
DOI is `10.14359/4181`; its pages are 605–615. This review read the abstract and
database record, not the original article's drawings or full methods.

Therefore the existing 866-pair A1 intake is not yet an admitted independent
validation model. Flexural classification alone does not establish an adequate
confined/high-strength material law or complete cyclic recovery. The published
eight-bar layout, cover definitions, measured material response, setup and source
rights still require original-detail review. No guessed geometry or constitutive
parameter has been inserted, and no experimental row entered learning here.

## Source CI remains separately attributed

At published source `8e45e4648603e12e59c3836a5157ff9dee2956ea`,
[Repository Python Tests](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34737623900)
collected successfully, then all four full-shard jobs failed. Inspected original
shard-0 log (job `103671705077`) stops in evidence preparation and names
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. No full-shard numerical-test
pass is inferred. The development-contract job was still running when inspected.
These results precede the alias change; no external receipt or tolerance changed.
