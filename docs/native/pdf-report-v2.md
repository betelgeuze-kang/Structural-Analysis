# Bounded embedded-font PDF report v2

## Closed profile

This additive C5 slice localizes the existing single-page nonlinear-NDTHA and sparse-linear
reports for exactly `en-US` and `ko-KR`. It does not alter either frozen v1 path: absent `--locale`,
each CLI command still emits its byte-identical v1 PDF and typed receipt. An explicit
locale selects the matching v2 profile:

```text
structural-cli report render-pdf \
  result-ir.json report-ir.json report.md \
  --output-dir localized-report --locale ko-KR

structural-cli report render-sparse-pdf \
  result-ir.json report-ir.json report.md \
  --output-dir localized-sparse-report --locale ko-KR

structural-workbench report-export-pdf \
  --workspace SESSION --output-dir localized-report --locale ko-KR
```

All entrypoints strictly re-project and byte-verify the profile-specific ResultIR, ReportIR, and
Markdown. The Workbench entrypoint additionally reproduces the durable v1 PDF and receipt before
exporting, leaves either NDTHA or `model_ir_linear_cpu_v1` session unchanged, and publishes only
to a new directory.

## Embedded font and deterministic bytes

Rust directly embeds `StructuralReportKoreanSubset.ttf`, a renamed subset of the OFL-1.1
`NanumGothic.ttf` source. The checked-in provenance records the original and subset SHA-256,
length, glyph inventory, license, and removed Reserved Font Names. The subset contains all
printable ASCII plus only the fixed Korean labels used by this report. Its primary family and
PostScript names are `Structural Report Korean Subset` and `StructuralReportKoreanSubset`.

The PDF 1.7 object graph uses a Type0 font, CIDFontType2 descendant, Identity-H encoding, embedded
FontFile2, contiguous CID-to-glyph identity map, explicit advance widths, and a ToUnicode CMap.
Every page string is emitted as deterministic hexadecimal CIDs. Dynamic case identifiers and
hashes are limited to non-empty printable ASCII dynamic values; unsupported glyphs fail closed.
The validator checks all ten object/xref offsets, trailer bindings, required font/CMap markers,
and exact embedded font bytes.

FontTools 4.61.1 was used once to create the checked-in language-neutral binary asset and generated
Rust glyph table. It is not a production, build, test, package, or runtime dependency. Generation
does not consult a host font or network. The product path invokes no Python, Node, browser, office
software, host font lookup, subprocess, or external renderer.

## Receipts and verification

Localized output contains `report.pdf` and a canonical typed receipt. Nonlinear NDTHA uses
`structural-native-localized-pdf-report-receipt.v2`; sparse linear uses
`structural-native-sparse-linear-localized-pdf-report-receipt.v2` and the explicit
`sparse_linear_cpu_v1` profile. Each receipt binds locale, source ResultIR, ReportIR, Markdown,
PDF, embedded-font identity, OFL-1.1 license, provenance path, artifact length, and its own unsigned
canonical hash. Clean-environment CLI and Workbench E2E prove repeated bytes are identical, locale
outputs differ, an existing destination is preserved, an invalid locale is rejected, and localized
export does not mutate the durable Workbench. Distribution E2E v7 binds the original NDTHA locale
surface; append-only v15 binds the installed ModelIR-linear locale surface without widening frozen
v1-v14 receipts.

Poppler is verification tooling, not a product dependency. `pdfinfo` recognizes one A4 PDF 1.7
page, `pdffonts` reports an embedded CID TrueType font with Unicode mapping, `pdftotext` reconstructs
the complete Korean authority statement, and a rendered PNG was visually checked for legibility,
alignment, overlap, clipping, header/footer placement, and page numbering.

## Authority boundary

This is fixed-label localization, not arbitrary Unicode or general Korean text input. It does not
claim PDF/A, tagged PDF, PDF/UA, WCAG or assistive-technology conformance, general application
localization, multipage tables/charts, signatures, engineering acceptance, or design-code
compliance. The durable Workbench v1 PDF remains ASCII-only by design. Broader report profiles,
approved-device HIP C2 parity, clean-machine release evidence, and final C6 decommission remain
open. Both fixed source profiles are localized; other report families remain open.
