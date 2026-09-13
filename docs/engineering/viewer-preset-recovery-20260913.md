# Workspace preset error recovery — 2026-09-13

The workspace model loader called an undefined `initLog` inside its preset error
handler. A missing preset therefore threw a new exception before attempting the
declared workspace artifact, reaching the outer emergency demo fallback. The
undefined call is removed; the existing warning remains, and the loader can
continue its declared artifact and subsequent source resolution.

Source: `8391374c7430395ff86b24dc6502adc3b800a6e3`.
The added test executes the actual loader function extracted from the HTML with
controlled I/O and normalization dependencies. Before the fix it reproduced
`ReferenceError: initLog is not defined` under Node 24.20.0. After the fix it
confirms that a valid preset stops further reads, a failed preset permits a valid
declared artifact with its original provenance, and failure of both returns null
with warnings. These are routing tests using synthetic payload markers, not
physical model validation. The focused loader/workspace suite passed three tests;
Ruff and diff checks passed. The loader test is already included in the structure
viewer contract verifier. No new-head hosted CI pass is claimed.

The trusted frontend launcher also passed TypeScript checking, production build,
viewer delivery checks and one targeted browser rejection test. A subsequent
actual loopback observation used the new production build at 1440 px, without
intercepting browser requests. Console records show the expected preset warning,
then attempts to read the declared workspace artifact, explicit preset and
embedded/candidate artifacts. No undefined-logger error was recorded. The RC
price-order panel remained verified: 42 exact original HTTP responses and 14
exact original downloads, with zero new solver calls or fits.

The review interval was 5.375645905 s, including 250 ms pacing before each download.
It excludes server/browser startup, screenshots, teardown and historical numerical
work; it is not a speedup result. Missing companion resources in this disposable
host still return 404. Drawing-comparison/catalog errors, demo/default data and
software WebGL remain separate limitations. This repair proves continuation of
the error path; it does not supply missing files or establish real-data viewer,
GPU, independent physical or product readiness.

Read-only observation packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-viewer-preset-recovery-Sm2ZpV`.
Six files / 252,017 bytes; inventory SHA-256
`16ea94e779d9bcdd0113b8fae6bf33d3f3270441621f2abc8f765ee0b17df183`.
It retains the observer, screenshot, action and console records, HTTP receipt
and full summary. See the [machine-readable record](viewer-preset-recovery-20260913.summary.json)
and [preceding Workbench observation](rc-layout-pruned-workbench-20260913.md).

The subsequent [runtime asset delivery fix](viewer-runtime-delivery-20260913.md)
includes the original dynamically loaded data in production builds and verifies
the default preset's non-demo source. Separate code-check/comparison gaps remain.
