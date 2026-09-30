# Continuous-rebar controls: source identity and model compatibility

The two continuous-rebar controls in Zenodo 1205887 remain **outside training and
physical validation**. Original-source review establishes a registered dataset
license and a useful specimen shortlist, but also exposes an unresolved source
conflict. It does not establish a compatible lateral flexural benchmark.

## Acquired sources and terms

The [DataCite DOI record](https://api.datacite.org/dois/10.5281/zenodo.1205887)
declares CC BY 4.0 for the versioned dataset, related to concept DOI 1205886.
This improves the earlier metadata-only licensing state. Archive contents and
file-specific notices remain uninspected; the dataset declaration does not license
the separately acquired thesis.

The Zenodo API, JSON export and specimen-description PDF each returned HTTP 504.
All three failed fetch receipts remain in the packet. The two large control ZIPs
were not downloaded. Instead, the [author's EPFL thesis](https://infoscience.epfl.ch/server/api/core/bitstreams/60b21868-9a38-4c19-a8f7-85d078f108a5/content)
was retrieved successfully: Danilo Tarquini, thesis 9432, 2019, 160 PDF pages.
Chapter 5 explicitly identifies this dataset DOI. PDF pages 90, 91, 92, 93, 94,
98, 101, 132 and 154 were rendered and visually inspected.

## Specimen correspondence

Table 5.1, page 90, reports both controls as 1,260 mm tall, with a 200 mm square
section and four continuous 14 mm longitudinal bars:

| Original label | Hoops | Approximate confinement ratio | Loading protocol |
| --- | --- | --- | --- |
| LAP-C1 | 6 mm at 200 mm | 0.15% | C1 |
| LAP-C2 | 6 mm at 100 mm | 0.3% | C1 |

These are axial tension-compression tests. The nominal C1 protocol uses a 10:1
displacement ratio; page 94 states actual manually stopped histories differed.
Page 98 records crushing, buckling and later bar rupture. Page 154 discusses
anchorage strain penetration and steel-concrete slip before failure.

There is an unresolved **within-thesis identity conflict**: section 7.4.1 on page
132 labels its continuous-rebar model LAP-C1 but states approximately 0.3%
confinement, whereas Table 5.1 assigns 0.15% to LAP-C1. Neither value is corrected.
Figure 5.1 on page 91 is explicitly LAP-P1 and must not become a control drawing.
Per-specimen files are still needed to establish archive-name correspondence.

## Admission decision and next work

Removing a splice does not establish that the full measured response is suitable
for the current public RC model. That profile uses its own axial-curvature fiber
section and uniaxial constituent laws; separate bond-slip or confined-concrete
modules elsewhere in the repository do not prove integration or qualification of
this experimental setup. Source inspection is bound to Git head
`bae1434e380164a552c440c89fd99dd7bec279cd` and five original module blobs.

The next acquisition should target specimen descriptions, lab books, material
coupons, actual histories, sensor definitions and interface measurements. It must
resolve the control identity before model reconstruction. No nominal target
sequence, calibration parameter, sign convention or supposedly compatible
pre-failure subset is manufactured from this review. Any future subset requires
declared physical scope and traceable original row indices.

The full campaign is kept as one conservative provenance group; no train/test
partition is assigned. Mirrored papers, repeated coupon files and the two control
specimens do not create independent campaigns. Experimental numeric rows acquired,
solver calls and fits in this intake are all **zero**. The running repeated-runtime
study and its frozen inputs are untouched.

## Verification and retained packet

The source audit checks original PDF and DOI-response bytes against fetch hashes,
the registered DOI/license/version relation, both extracted table rows, the
conflicting passage, source-to-dataset reference, and five exact Git blobs. These
are source-consistency checks, not independent physical validation. The inspection
shares the runtime-study host; no exclusive-host timing is claimed.

Sealed packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-zenodo-continuous-controls-38akyx74`.
It contains **27 files / 19,893,889 bytes**, reread with exact hashes; inventory
SHA-256 is `c37384794ed4a85e13bafd191dbb60cc298b44d2f29f5396299ba771d1048f12`.
Inventory and seal files are excluded from payload totals. Original PDF/images
remain in this local packet rather than being republished with the code.
[Machine summary](zenodo-continuous-controls-20260910.summary.json).
