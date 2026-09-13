# Public-source expansion: lineage before case count

Review date: 2026-09-13; repository source
`8e45e4648603e12e59c3836a5157ff9dee2956ea`.
This is a primary-page discovery review, not a downloaded or admitted corpus.
No source files, numerical labels, training splits or solver behavior changed.

## New archive lead and an explicit overlap

The publisher's [ACI 369 rectangular column resource](https://datacenterhub.org/resources/255.html)
identifies DOI `10.4231/D36688J50` and explicitly says that it builds on PEER,
which in turn built on NIST collections. It describes tabular geometry,
reinforcement, material strengths and lateral load-deflection files. Therefore
ACI, PEER and NIST are not automatically independent experimental cohorts.
Additional ACI records may be useful, but their novelty is not established here.

The [legacy directory](https://datacenterhub.org/nees.html) links the archive to
a public Dropbox folder. Following the publisher's View Data link reached a
Dropbox page, but the browsing tool exposed no file listing. No CSV was acquired
or counted. The resource's rendered "Licensed under" field supplied no license
text; reuse status remains unresolved. This does not establish that no license
exists elsewhere. No third-party paper's license is transferred to these data.

Next acquisition should obtain the archive manifest and row identities, then
crosswalk original author/year/report/specimen against the
[already acquired PEER table](peer-spd-source-intake-20260909.md). Preserve
conflicting identifiers and property values. Do not identify a specimen solely
by its geometry or a similarly named curve. Until the crosswalk is reviewed,
the number of additional independent campaigns stays unknown.

## A separate experimental candidate remains incomplete

The official [CORA UPC collection](https://dataverse.csuc.cat/dataverse/UPC)
lists [Column-to-foundation connection test](https://doi.org/10.34810/DATA3379),
version 2, by Vidovic, Carevic and Milicevic. Its description names two recycled
aggregate concrete cantilever columns and two CSV/two JPEG files for cyclic and
monotonic testing. These are publisher-described contents, not inspected files.
The direct dataset-page request timed out. The API URL was rejected by the
browsing tool and was not retried through another execution route.

The collection lists multiple license categories; none can be assigned to this
record from collection-level facets. Material response, reinforcement coordinates,
connection behavior, sensor mapping, axial loading and commanded history remain
unverified. Neither membership in a new repository nor the word "cantilever"
establishes compatibility with the current fiber element. Keep this as a lead,
not a selected flexure-only benchmark or a new training case.

## Existing source roles are unchanged

The [earlier intake](rc-public-data-intake-20260909.md) already separates papers,
measured response, numerical simulations and drawings. A fresh check of the
[CubiCasa5K publisher repository](https://github.com/CubiCasa/CubiCasa5k) and
[license](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) confirms the
floorplan-recognition scope and CC BY-NC 4.0 notice. It is not a source of verified
reinforcement, loading or structural-response labels, and is not admitted to an
unrestricted commercial training inventory. No drawings were downloaded.

Zenodo numerical corrosion record `19117993` was already inventoried. A new
landing-page timeout and rejected API URL supply no new file evidence; its
previous simulation-source classification is unchanged. Previously unsupported
shear, bond-slip and confinement cases were not rerun or fitted in this review.

## Concrete next experiment, after source admission

1. Resolve one complete source campaign and its archive mirrors; identify the
   original specimen and reuse terms before generating a canonical model.
2. Match the implemented mechanism, reinforcement layout, force convention,
   boundary conditions and full loading history. Retain missing fields rather
   than filling them with convenient defaults.
3. Freeze campaign-level calibration/training/evaluation assignments before
   fitting materials, preprocessing or selecting strategies. A calibrated
   experimental curve cannot also be untouched external validation.
4. Compare the baseline model with measured response. Generate solver-state and
   work labels separately: a measured top-displacement curve does not supply
   every nodal coordinate or Newton history.
5. Evaluate the proposed strategy against secant on complete unseen paths with
   unchanged acceptance checks, counting feature extraction, rejected proposals,
   fallback, reanalysis and training separately. Retain failed paths and unknown
   costs. More downloaded rows alone do not demonstrate speedup.

Result of this review: one explicit archive-lineage dependency and one separate
candidate lead, **zero acquired experimental files and zero admitted training
rows**. No independent physical validation or learning benefit is claimed.
