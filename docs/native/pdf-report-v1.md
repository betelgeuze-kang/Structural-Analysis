# Bounded Native PDF Report v1

## Closed profile

This slice closes C5 only for a single-page A4 summary of the bounded CPU nonlinear-NDTHA
`ResultIR`. Rust re-projects the expected ReportIR and Markdown from the supplied ResultIR and
requires exact byte identity before rendering. A separately self-consistent but forged ReportIR
or document source is rejected.

The renderer emits deterministic PDF 1.7 bytes with fixed Helvetica, Helvetica Bold and Courier
standard fonts, no wall-clock metadata, no compression variability and a document ID derived from
the source ResultIR. The page contains:

- analysis case, terminal status, completed steps and response summary;
- ResultIR, ReportIR, document, request, model, state, execution and checkpoint hashes;
- backend, FP64 determinism and fallback count;
- an explicit bounded-candidate authority boundary and page number.

The native validator checks the PDF header/binary marker, all eight fixed-width xref entries,
object offsets, catalog/info/size trailer bindings, `startxref` and EOF. The public CLI publishes
the PDF and a self-hashed receipt through a create-new directory boundary:

~~~bash
structural-cli report render-pdf \
  result-ir.json report-ir.json report.md \
  --output-dir pdf-report
~~~

The E2E clears the child environment, including `PATH`, and proves repeated PDF and receipt bytes
are identical without Python, Node, Chromium, office software or an external PDF renderer. The
frozen profile is also inspected with Poppler during implementation: `pdfinfo` recognizes one A4
PDF 1.7 page, text extraction contains every required field, and a rendered PNG has no clipping,
overlap or illegible text. Poppler is verification tooling, not a product dependency.

## Authority boundary

This slice does not claim PDF/A conformance, tagged accessibility, Unicode or localized fonts,
forms, signatures, multipage tables/charts, broader ResultIR profiles, engineering acceptance or
design-code compliance. HIP C2 source-result parity and final C6 decommission also remain open.
The Workbench's separately verified `en-US`/`ko-KR` UTF-8 linear report view is a terminal text
alternative. A separate opt-in embedded-font v2 renderer now provides fixed-label `en-US`/`ko-KR`
PDF export without changing this frozen default; see `docs/native/pdf-report-v2.md`.
