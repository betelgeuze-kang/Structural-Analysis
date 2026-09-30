# Tan/Nguyen controls: original-source reconciliation

Two rows from the pinned [Zenodo table](zenodo-8062007-original-20260920.md) were
traced to the [publisher's original paper](https://stce.huce.edu.vn/index.php/en/article/view/1319),
DOI `10.31814/stce.nuce2019-13(1)-01`. PDF pages 3, 4 and 8 were visually inspected.

| Check | Finding |
| --- | --- |
| D10-1, CSV row 679, tensile yield strength | CSV 334.0 MPa; paper Table 2 gives D10 337.3 MPa |
| D8-1, row 676 | Peak 27.59 kN and ultimate displacement 18.11 mm match Table 4 |
| D10-1, row 679 | Peak 36.39 kN and ultimate displacement 13.44 mm match Table 4 |
| Stirrups | Materials text says D6; design text/drawing specify D4 |
| Spacing | CSV 150 mm; design text distinguishes 150 mm end regions and 300 mm middle |
| Endpoint labels | Table 4 contains cracking/peak quantities; it does not establish CSV yield columns |

The publisher lists CC BY-NC-ND 4.0, separately from the Zenodo record's CC BY 4.0.
Keep source-specific rights attached; no broader authorization is inferred.

Both specimens belong to one source experiment group. Their reviewed status is
recorded, no untouched-evaluation status is claimed, and split assignment remains
null. Original CSV bytes remain unchanged. The conflicting value is recorded as
a reconciliation issue, not silently repaired. No fits, solves or physical
validation are performed. Admission still requires resolved provenance, model
inputs and response-history/measurement definitions.

The separate packet contains original publisher HTML/PDF, extracted text, three
inspected pages and reconciliation JSON:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-tan-2019-yhz_2qpe`.
Seven payloads, 2,606,624 bytes; inventory SHA-256
`1dffa709bd20224c3730f06339d8539e7c8033975f454058a97fde08a05f212f`.
PDF SHA-256: `8be093427a9dbf556597700040cf245789f5ab88c261bf95aeba4c0425e14e1a`.
The adjacent summary retains both original row identities and each unresolved
comparison. This evidence narrows source uncertainty without substituting for
independent solver verification or training admission.
