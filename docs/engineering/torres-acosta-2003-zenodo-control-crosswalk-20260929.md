# Torres-Acosta (2003) control beams: source-to-table boundary

This is a source-only crosswalk for rows 161 and 162 of the original
[Matthews, Palermo and Scott Zenodo database](https://doi.org/10.5281/zenodo.8062007).
The two rows name the uncorroded V01 and V02 specimens in
[Torres-Acosta, Martínez-Madrid and Muñoz-Noval (2003)](https://doi.org/10.3989/mc.2003.v53.i271-272.297).
Neither row is admitted for training or independent endpoint validation.

## Source identity and access

The official Zenodo API lists `Database.csv` as 482,117 bytes, MD5
`aadaa12311cb4a09703337aca90b6dc7`, and `Database Key.pdf` as 277,488
bytes, MD5 `7b67fff0b9f774d50811e53619fd0609`, with CC BY 4.0 metadata.
Direct official-file reads matched both MD5 values; their SHA-256 values are
`a37641e015c0e7052e9450d5530935594a3a13cbfb83296952e4bc0bd06aa8a9`
and `7301e815518571d289024c16ede86973413c52173b03d1b1a8f4149c623e7c0d`,
respectively. The CSV has 804 numbered specimens. This crosswalk uses the
original numbered rows, not a reduced derivative table.

The [publisher's article page](https://materconstrucc.revistas.csic.es/index.php/materconstrucc/article/view/297)
identifies the DOI and links the [publisher PDF](https://materconstrucc.revistas.csic.es/index.php/materconstrucc/article/download/297/342/413).
The PDF is image-based: visual inspection covered printed pages 126–132,
including Figure 1, Table 1 and Figure 2. Its local diagnostic download was
1,438,831 bytes with SHA-256
`71407cd315061990641038d6c484ead719803f897234a1db382163035a76eaf1`.
The publisher endpoint failed TLS certificate-chain verification in this
environment. These bytes were therefore retrieved with TLS verification
disabled; this hash is a local retrieval identifier, **not** a publisher
checksum or authenticated source attestation. No paper PDF or figure is
included in Git.

## Specimen and endpoint crosswalk

| Field | Original article | Zenodo rows 161 / 162 | Boundary |
| --- | --- | --- | --- |
| Identity | V01 and V02 are the two uncorroded controls in printed Table 1. | `Torres-Acosta et al. (2003), V01` / `V02`; corrosion method `C`. | Identity and noncorroded status correspond. Keep the entire experiment family together in any later split. |
| Geometry | Printed page 126 and Figure 1 give a 100 × 150 × 1,500 mm beam and one nominal #3 (10 mm) tensile bar; Figure 1 depicts a 9.5 mm actual bar and 20 mm surface cover. | Width 100 mm, depth 150 mm, length 1,500 mm, one 10 mm bar, bottom cover to bar centre 25 mm. | Nominal dimensions and cover-to-centre arithmetic agree (`20 + 9.5/2 ≈ 24.75` mm). A 6 mm internal cathode rod is also depicted; its condition-specific structural role is not resolved. |
| Supports and load | Printed page 128 states simple support on a steel I-beam, one centred actuator load, and 1 mm/min machine-head movement. | `SS_TPB_MONO`, `Test Length=1500 mm`, `Shear Span=750 mm`. | The paper establishes three-point loading, but the inspected pages do not measure the support-centre span. The table's 1,500 mm test span and 750 mm shear span cannot be authenticated from the 1,500 mm **overall beam length** alone. |
| Concrete and steel | Printed page 127 gives water/cement ratio 0.5, Type I Portland cement, 19 mm maximum aggregate, and **37 MPa average 28-day strength from four cylinders**. The inspected article pages identify the bar diameter but give no specimen-specific steel coupon result. | Cylinder strength 37 MPa, `fy=415 MPa`, `fsu=664 MPa`. | Concrete strength is a tested batch average, not a separate V01/V02 measurement. The original-paper basis of the two steel strengths is unresolved; a populated table cell does not prove a measurement. |
| Recorded displacement | Printed page 128 and Figure 2 describe actuator or machine-head movement. | V01 ultimate displacement blank; V02 `Δult=10.00 mm`. | Machine-head travel is not a measured midspan beam deflection; fixture and support compliance cannot be silently removed. No ordered numeric load–deflection file accompanies this paper crosswalk. |
| Failure label | The inspected original Table 1 and Figure 2 do not assign the table's ductile/brittle labels to V01/V02. | V01 `Flexural-bending (ductile)` and its Extra Notes explicitly say failure mode was **assumed**; V02 `Flexural-bending (brittle)`. | Neither label establishes a verified flexure-only failure mechanism for this solver. |

Printed page 129 Table 1 lists `P_MAX=9.1 kN` for V01 and `10.8 kN` for V02.
Printed page 131 uses their 9.95 kN average for the paper's residual-capacity
ratio. Although the table footnote calls `P_MAX` the maximum load recorded,
page 130 defines it at a point just before transverse flexure cracking and
steel yielding; Figure 2 continues beyond that point for V02. The source
therefore does not supply one unambiguous numerical *ultimate-load* endpoint.

The CSV places 9.10 and 10.80 kN in `Py`, leaves V01 `Pmax` blank, and gives
V02 `Pmax=11.60 kN`. Its `Mmax,exp` values are 3.41 and 4.05 kNm. With the
CSV's assumed 1.5 m support span and a centred single point load,
`P × L / 4` gives `9.1 × 1.5 / 4 = 3.4125 kNm` and
`10.8 × 1.5 / 4 = 4.05 kNm`: the reported moments track the article's
Table 1 `P_MAX` values, stored as `Py`. Using V02's CSV `Pmax=11.6 kN`
instead gives **4.35 kNm**, 0.30 kNm above its `Mmax,exp` cell. The original
article Table 1 does not provide that 11.6 kN number as a tabulated endpoint,
and this audit does not assign it a measured origin from the raster plot.
Thus `Mmax,exp` is an arithmetic derivative of a differently named load and
an unverified span, not a directly reported ultimate moment.

## Rights and admission decision

The publisher's current article page states CC BY 4.0. The distributed PDF
itself carries a CC BY-NC 3.0 Spain footer. The Zenodo compiled table separately
declares CC BY 4.0. These notices conflict for reuse of the *article's* PDF,
figures or derived plotted values; this crosswalk does not decide which governs
commercial reuse or grant training permission from one notice to another.
It cites and paraphrases the article without republishing its pages.

**Decision: held, zero admitted training rows, zero admitted evaluation rows,
zero structural solves and zero independent physical validations.** Before a
numeric benchmark is defined, confirm the support-centre geometry, steel
material provenance, event meaning of the two load columns, numerical raw
load/displacement channels and their machine-versus-specimen locations, failure
mechanism, and applicable reuse terms. Predeclare any later endpoint and keep
these specimens held out by original experiment family; do not fit material
parameters from V01 or V02 and then call their comparison independent.
