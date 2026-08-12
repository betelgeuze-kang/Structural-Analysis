# Bounded Native Product E2E v1

## Closed profile

This slice closes C5 only for the tracked serial-FP64 CPU nonlinear-NDTHA request profile. The
public command accepts a strict, result-free `structural-native-analysis-request.v1`, executes the
C++ kernel through ABI v1.5, binds the terminal state to the C4 checkpoint identities and emits:

- `checkpoint.ndcp`: complete resumable state;
- `result-ir.json`: canonical, self-hashed `bounded_candidate` ResultIR;
- `report-ir.json`: canonical ReportIR bound to the exact ResultIR and document source;
- `report.md`: deterministic PDF-ready document source;
- `run-receipt.json`: self-hashed inventory with byte count and SHA-256 for every artifact.

An active step budget publishes only the checkpoint and run receipt. Supplying that checkpoint to
`analysis resume` produces exactly the same terminal five files as a direct run. Publication builds
and syncs a new sibling directory before one rename; an existing destination is never overwritten.

## Commands

~~~bash
structural-cli analysis run request.json --output-dir run
structural-cli analysis run request.json --output-dir partial --step-budget 2
structural-cli analysis resume request.json partial/checkpoint.ndcp --output-dir resumed
~~~

The E2E test clears the child process environment, including `PATH`, before invoking the absolute
Rust binary. Direct and resumed checkpoint, ResultIR, ReportIR, Markdown and receipt bytes are
identical. The request and all five terminal artifacts have frozen SHA-256 values.

## Authority boundary

The result remains `bounded_candidate`. This slice does not claim broader dynamic solver coverage,
HIP C2, a ModelIR-to-analysis adapter, distributed durable jobs/API, tenant authorization, native
Workbench or C6 removal. Separate bounded C5 slices now own local durable-job submit/poll/cancel/
crash reconciliation, three global external-comparison quantities and a single-page native PDF,
but they do not broaden this synchronous product claim or close live external-solver/same-mesh,
PDF/A or accessibility gates.
