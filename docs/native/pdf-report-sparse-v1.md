# Bounded sparse-linear native PDF report v1

## Closed profile

This additive C5 profile renders one converged bounded sparse-linear `ResultIR` as a deterministic
single-page A4 PDF 1.7. It does not alter the frozen nonlinear-NDTHA v1 or localized v2 bytes.
Rust rebuilds the exact sparse `ReportIR` and Markdown from `ResultIR`; independently forged or
merely self-consistent report inputs fail before PDF construction.

The public entrypoint is explicit about the accepted result family:

```text
structural-cli report render-sparse-pdf \
  result-ir.json report-ir.json report.md \
  --output-dir sparse-pdf-report
```

The `model_ir_linear_cpu_v1` Workbench profile calls the same product-library function directly.
Its Report stage atomically publishes ResultIR, typed recovery IR, ReportIR, Markdown, PDF, the
sparse PDF receipt, and a Workbench report-stage receipt. Review and Export bind both the PDF and
its source Markdown.

## Determinism and validation

The page contains the case, matrix order, canonical nonzero count, PCG iterations, final true
residual, CPU/FP64 policy, fallback count, and the exact ResultIR, ReportIR, document, request,
model, state, execution, and checkpoint hashes. Standard Helvetica, Helvetica Bold, and Courier
fonts avoid host-font lookup. There is no clock metadata, compressor variability, process launch,
Python, Node, browser, office software, or external renderer.

The existing native validator checks the fixed eight-object graph, PDF header and binary marker,
every xref offset, catalog/info/size trailer binding, source-derived document ID, `startxref`, and
EOF. The CLI emits `structural-native-sparse-linear-pdf-report-receipt.v1`; the Workbench embeds
that receipt as a hash-bound artifact in
`structural-native-model-ir-linear-pdf-report-receipt.v1`. Clean-environment tests prove repeated
bytes, direct/restart identity, wrong-profile rejection, and one-byte PDF tamper rejection.

## Authority boundary

This is a bounded sparse CPU candidate summary, not engineering acceptance or design-code
compliance. It does not claim localized sparse-linear PDF, arbitrary Unicode, PDF/A, tagged PDF,
PDF/UA, WCAG or assistive-technology conformance, multipage tables/charts, signatures, approved
HIP C2 parity, broader report profiles, or C6 decommission.
