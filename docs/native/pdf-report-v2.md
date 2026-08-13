# Bounded embedded-font PDF report v2

## Closed profile

This additive C5 slice localizes the existing single-page nonlinear-NDTHA report for exactly
`en-US` and `ko-KR`. It does not alter the frozen v1 path: absent `--locale`, the CLI still emits
the byte-identical v1 PDF and receipt. An explicit locale selects v2:

```text
structural-cli report render-pdf \
  result-ir.json report-ir.json report.md \
  --output-dir localized-report --locale ko-KR

structural-workbench report-export-pdf \
  --workspace SESSION --output-dir localized-report --locale ko-KR
```

Both entrypoints strictly re-project and byte-verify the exact ResultIR, ReportIR, and Markdown.
The Workbench entrypoint additionally reproduces the durable v1 PDF and receipt before exporting,
leaves the session unchanged, and publishes only to a new directory.

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

Localized output contains `report.pdf` and canonical
`structural-native-localized-pdf-report-receipt.v2`. The receipt binds locale, source ResultIR,
ReportIR, Markdown, PDF, embedded-font identity, OFL-1.1 license, provenance path, artifact length,
and its own unsigned canonical hash. Clean-environment CLI and Workbench E2E prove repeated bytes
are identical, locale outputs differ, an existing destination is preserved, an invalid locale is
rejected, and localized export does not mutate the durable Workbench. Distribution E2E v7 repeats
both locale exports through the installed Workbench with an empty lookup path and binds the PDF,
receipt, installed font, OFL notice, and provenance identities into the package receipt.

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
open.
