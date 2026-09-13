# PEER multi-campaign originals and curated drawing references

The existing source decoder at `9a9c26833f043f9338ef41017b9b14139270dd47` now has an actual
intake audit for five additional named experimental histories. Every original
token and exact decimal value in **5,650 pairs** is checked independently of
the decoder's conversion. Each XML record ID/version, source history link and
specimen name binds to its property-table row; **40 selected numeric property
pairs and units** agree. These five histories have two columns, so no axial
history is invented from a constant scalar or a paper title.

| Source ID | Original table name | Measured pairs | Axial channel |
| --- | --- | ---: | --- |
| PEER-SPD-64 | Ono et al. 1989, CA025C | 1,083 | absent |
| PEER-SPD-65 | Ono et al. 1989, CA060C | 736 | absent |
| PEER-SPD-105 | Saatcioglu and Ozcebe 1989, U3 | 1,010 | absent |
| PEER-SPD-181 | Matamoros et al. 1999,C5-00N | 1,955 | absent |
| PEER-SPD-201 | Thomsen and Wallace 1994, A1 | 866 | absent |

Together with the separate sealed U1 packet, intake now covers six named histories
and 7,401 pairs. This count is not six admitted models or independent experiments.
Ono's two specimens share one local campaign group. U3 shares U1's group, and the
other two histories identify two further campaigns. All partition assignments
remain unassigned; source mirrors and same-campaign specimens must remain together
when splits are frozen before calibration or fitting. Original names, including
Thomsen/Thompson/Thomson spellings, are retained without fuzzy identity assignment.

## What the additional original-source inspection changes

The [NISTIR 5984 report](https://nehrpsearch.nist.gov/static/files/NIST/PB97153522.pdf)
is a curated summary, not the original experimental paper. Its printed pages
26, 38 and 39 were rendered and visually inspected:

- The selected Ono CA025C/CA060C tests used constant compression. The paper also
  studied varying load, but those specimens are excluded from this reported subset.
- U3 has a documented section sketch and material/reinforcement table. NIST states
  the reported U-series digital histories came from the original researchers;
  lineage from those WK1 files to today's TXT files is not yet established.
- U1 is explicitly excluded there. The U3 drawing cannot resolve U1's missing
  drawing or its existing wide-hoop conflict.
- U3's printed longitudinal ratio is 0.0327, versus PEER's 0.0321. The printed
  transverse ratio 1.69 versus PEER's 0.017 also needs unit/definition review.
  Neither source value is overwritten or automatically rescaled.

These findings refine specimen selection and provenance. They do not reconstruct
a fully verified material law, commanded loading protocol or analytical model.
Unmeasured constitutive parameters must be explicitly identified as model/calibration
assumptions, with calibration confined to the declared partition, rather than
being presented as measured material properties.

The [Matamoros dissertation record](https://www.ideals.illinois.edu/items/84770)
restricts original downloads to the Illinois community; no full dissertation was
retrieved. The direct metadata fetch also returned 403 and that failure is retained.
A new [refined-column-data paper](https://ascelibrary.org/doi/10.1061/JSENDH.STENG-14725)
links a [Figshare repository](https://figshare.com/s/341e5941ace7b2f0c9ad), but the
repository returned a browser 403 and then an empty HTTP 202 to the local fetch.
Its files and license remain unverified. Re-curation is not a new independent test
campaign and would require matching originals before combination with PEER.

## Audit and evidence

The actual audit exits zero: internal **0.039978212 s**,
parent **1.464858217 s**, with no Newton solve, fitting,
material integration, compilation or native commit. The first audit attempt
incorrectly required optional thesis metadata availability; its source and failed
log remain. The corrected scope still requires successful HTTP 200 outcomes and
exact hashes for every original XML/history/reference file. No original value,
count, decoder behavior or numerical acceptance gate changed.

The new source packet is `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-peer-cohort.cz2yewo9`:
**31 files / 4,095,218 bytes**, all reread exact, inventory
SHA-256 `737c5d08e6f7630a3a699e70b7c6e31bb0119a86d969cf09f811408672e58428`. Inventory/seal files are excluded from
payload totals. The original U1 and axial-format packets remain unchanged.
These lightweight checks and fetches share the learning-repeat host; no
exclusive-host timing is claimed. [Machine audit and campaign identities](peer-spd-cohort-intake-20260909.summary.json).

External training admission and independent physical validation remain false.
Reuse terms, compatible reconstruction, source conflict review, calibration
assumptions and frozen project/campaign partitions remain necessary next work.
