# Soesianawati No. 1: specimen inputs and force convention

This follow-up establishes additional source correspondence for the flexural
cohort screened in the [earlier intake](soesianawati-source-correspondence-20260910.md).
It does not admit experimental rows to training or validate the fiber model.

## Sources actually inspected

The [Canterbury item](https://ir.canterbury.ac.nz/items/9253a543-e522-4f64-9dde-6148c54036ba/full)
identifies Soesianawati's 1986 thesis, DOI `10.26021/2554`, and a public
[download link](https://ir.canterbury.ac.nz/bitstreams/7b30cecb-c23d-4efc-8219-a4a39a04e82f/download).
The item was read through the browser. HTTP downloads returned challenge pages,
the web reader rejected the PDF's size, and the browser download was blocked.
The original full text remains unread. The item reserves copyright for private
study/research; public accessibility is not recorded as redistribution permission.

The [NIST publication record](https://www.nist.gov/publications/summary-cyclic-lateral-load-tests-rectangular-reinforced-concrete-columns)
links NISTIR 5984, the compiler's account of its digitized column dataset.
The [official PDF](https://nehrpsearch.nist.gov/static/files/NIST/PB97153522.pdf)
was downloaded: 3,494,541 bytes, SHA-256
`2dbd0b88a3e8578c30f3de5e4b2728eb157b389d2d495be8f153109d8a951f0c`.
PDF pages 9, 11, 15, 49, 53 and 105 were rendered and visually inspected
(printed pages 1, 3, 7, 41, 45 and 97). NIST is authoritative for the conventions
of its compilation, but is a secondary account of the 1986 physical experiment.

## Inputs supported by the No. 1 table

Printed p.7 identifies No. 1 independently of the No. 4 drawing distributed with
the SimCenter example. Its common section sketch explicitly covers units 1-4.

| Input | NIST No. 1 value | Scope |
| --- | --- | --- |
| Section / equivalent length | 400 mm square / 1,600 mm | Equivalent cantilever |
| Longitudinal reinforcement | Twelve 16 mm bars, yield 446 MPa | Grade designation 380 is distinct |
| Concrete / axial compression | 46.5 MPa / 744 kN | Constant-load metadata |
| Hinge hoops | Five sets, 7 mm at 85 mm | No. 1, not No. 4's R6 at 94 mm |
| Outside hoops | Six sets, 7 mm at 170 mm | Exact zone endpoints remain open |
| Hoop yield | 364 MPa | Grade designation 275 is distinct |
| Cover | 13 mm clear to transverse bars | Not longitudinal bar-center cover |
| Transverse ratio | 0.0086 | PEER reports 0.009; both retained |

Sixty numeric fields across all four NIST rows match the sealed PEER XML records.
The four axial ratios also agree with `P/(fc * 400 * 400)` after unit conversion.
This checks transcription correspondence, not independent correctness of either
source. The [observer](soesianawati-nist-correspondence-20260910.audit.py.txt)
binds the original XML/history hashes and preserves both transverse ratios.

NIST p.3 warns that transverse reinforcement ratio definitions differ among
studies. Neither value is substituted automatically into a confinement law.
PEER stores its 13 mm value beneath longitudinal reinforcement; NIST explicitly
defines cover to the transverse bars. Exact bar-center coordinates, tie geometry
and confined-core dimensions need an explicit model mapping.

## Force conversion must happen only once

NIST pp.3 and 7 show central actuator force `2H` and explicitly report **H** in
the plots and data files. The double-ended specimen is normalized as a simple
cantilever: retain the central-stub displacement relative to the end supports and
use the 1.6 m equivalent length. Do not divide the normalized force or displacement
by two again. A whole double-ended model would instead require the corresponding
central applied force and its actual boundary conditions.

PEER identifies the configuration as double-ended and labels its force channel
`Shear provided`. That supports this interpretation, but the original NIST disk
was not obtained and its file bytes were not compared with the Washington copy.
The NIST plot identifies `SOES86U1.DAT`; the summary table lists `SOES86U1.WK1`.
The existing PEER-linked text has 744 pairs. No exact disk-to-host chain of
custody, force correction history or additional P-delta correction is inferred.

## Measurement and model limits

NIST p.1 says many histories were manually digitized from published plots, while
some came directly from researchers. It does not identify No. 1's acquisition
route here. Preserve these as an experimental response history with unresolved
acquisition provenance, not authenticated raw sensor samples or actuator commands.
Page 97 specifies title, count, then displacement-force pairs in mm and kN;
all 744 retained rows satisfy that format. No executable from the old disk ran.

PEER's damage metadata records crushing at 39.2 mm, spalling at 58.8 mm, buckling
at 78.4 mm, and fracture/axial-load loss at 98 mm. These are source annotations,
not accepted model validity thresholds. Full-history agreement cannot follow from
an Euler-Bernoulli label or fitting a preselected portion of the curve. Original
constitutive histories, loading protocol, geometric force mapping and supported
damage mechanisms remain necessary. No model input deck or calibrated material
parameters are created from these incomplete records.

The NIST text also has inconsistent overall specimen totals (93 on p.41 versus
107 on pp.1 and 97); this pass makes no complete-corpus count claim. NIST, PEER
and the 548-pair SimCenter subset remain one campaign lineage for splitting.

## Evidence and checks

The [machine summary](soesianawati-nist-correspondence-20260910.summary.json)
records the sealed packet, all fetch results, the six page
images, the source-bound correspondence observer and its results. There are
**60 matching numeric comparisons, four axial-ratio checks, 744 parsed pairs,
zero structural solves and zero training fits**. No physical-validation or
learning-performance claim changes. The packet is retained locally; only the
analysis, source links, summary and observer are committed.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-soesianawati-primary-mcjxytz9`,
21 files / 4,457,161 bytes; inventory SHA-256
`b4a734122697ba3e892231358672e34895719f1d357b730e7935cc944ce941e3`.
Every file was reread when sealing. The archived observer is the exact executed
script; reproducing it requires a fresh output packet and updated local paths.
Do not run it against the sealed packet or its current `/tmp` pointer.
