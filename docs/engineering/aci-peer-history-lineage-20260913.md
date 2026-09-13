# ACI and PEER A1 response-history lineage

The public ACI archive's `data/272.csv` was located through its rendered folder
listing and downloaded from the exact public file link. Its explicit header is
`Displacement (in.),Force(kips)`. The 17,813-byte original has SHA-256
`6b6e9df802f8d8cf13458ac454bf9129c0dab66c155564755f3f2dfd8dd2474e`.
The [earlier table review](aci-archive-table-intake-20260913.md) identifies this
record as Thomsen and Wallace A1, corresponding to PEER SPD 201.

Both original histories contain **866 ordered pairs**. Multiplication of ACI
displacement tokens by 25.4 gives exact Decimal equality with every PEER mm
token. The force channels are not exactly equal under the standard
4.4482216152605 kN/kip conversion: maximum absolute difference is
**0.001847457679920018585 kN**. Neither original is rewritten or designated as
an authoritative correction of the other.

A descriptive through-origin least-squares fit of the two force channels yields
4.448398576523328923444834696 kN per ACI force unit, with maximum residual
2.045587900124666091e-8 kN. This fitted scale describes these files; it is not a
validated unit definition, calibration, or evidence identifying which exporter
performed a conversion. The shared specimen citation, exact displacement sequence
and near-proportional force sequence strongly support common history lineage.
They must not be counted as independent experiments or split across training and
evaluation merely because their repositories and byte hashes differ.

The [machine summary](aci-peer-history-lineage-20260913.summary.json) records both
source hashes, comparison metrics and the external evidence inventory. The packet
retains raw acquisition, receipt and audit scripts outside Git; earlier sealed
packets remain unchanged. This is one source comparison, not an audit of all 326
ACI histories. There were no structural solves or model training fits. The
numerical scale fit above is solely a descriptive source comparison.

The [positional table reader](aci-positional-reader-20260913.md) still grants no
training admission. Original setup, material and confinement details, source reuse
terms and appropriate physical-model coverage remain unresolved. This result
supports reviewed campaign aliasing; it does not automatically authenticate or
merge arbitrary equal-name specimens.
