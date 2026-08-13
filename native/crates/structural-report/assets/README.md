# Embedded localized report font

`StructuralReportKoreanSubset.ttf` is a deterministic, renamed subset of
`NanumGothic.ttf`. It contains printable ASCII plus only the fixed Korean labels used by the
bounded native PDF v2 renderer. The Rust production, build, test, and packaging paths consume the
checked-in binary directly and do not invoke FontTools, Python, a host font lookup, or the network.

The exact origin and transformation identities are recorded in
`StructuralReportKoreanSubset.provenance.json`. The modified font remains licensed under OFL-1.1;
the copyright notice, Reserved Font Names, and complete license are in `OFL-1.1.txt`. The modified
primary family and PostScript names intentionally do not use a Reserved Font Name.

This is bounded localization coverage, not an arbitrary-Unicode font, accessibility claim, or
PDF/UA claim.
