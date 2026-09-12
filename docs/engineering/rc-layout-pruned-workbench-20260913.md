# Workbench cost-pruned layout review — 2026-09-13

Workbench now reads the separate cost-pruned layout report, verifies original
design records, recomputes the prior-row cost decisions, and displays evaluated,
cost-skipped and outside-horizon candidates separately. Unevaluated physical
feasibility stays unknown. Each pool model and each recorded decision can be
downloaded as original bytes, alongside the existing selected-design artifacts.

The worker retains validated pool/decision bytes for immutable downloads. It
continues to validate and recheck selected-design downloads with the layout
artifact paths. Review rejects altered decisions, future-row evidence,
inconsistent coverage, missing required rows and incomplete target-step work.
Raw JSON slices preserve the Python numeric spelling when checking evaluated-row
hashes. Predictions never establish an incumbent; verified full-reference rows
and passing requested limits are required. The original report is preserved.

The screen explicitly distinguishes the fixed consideration horizon from actual
executions. Skipping does not expand the horizon. Decision-processing time is
already inside the original strategy interval. Exhaustive coverage and cost
optimality remain null; the UI does not invent a zero cost gap or claim a pool
minimum. Existing standalone and two-arm report views remain supported.

## Verification and original fixtures

Source: `6442997dc12929cb288940355724725fa560c732`.
Trusted Node 24.20.0 ran TypeScript checking, production Vite build, viewer
delivery-contract checking, and the formal Workbench test launcher. The first
selection passed **60 layout contract/browser tests**, including 24 new cases.
A disjoint follow-up selection passed **44 tests**, including the new browser
case that hides all selections when a decision changes, existing search
contracts, and actual HTTP search tests. In total, 104 selected tests passed.
This is not the complete frontend or repository suite and is not current-head
hosted CI evidence. Build warnings about bundle size remain visible.

The [fixture provenance](../../tests/frontend/fixtures/rc-layout-pruned.md) records
three original graphs. Price order reuses the previously sealed actual execution.
New shortened-horizon and learned-order fixture runs reuse original inputs and
the existing learned policy. They add six reference rows / twelve analysis and
fresh-verification invocations / 72 target steps / 144 Newton iterations and
linear solves, with no new fit. Those preparation costs are separate from the
browser observation and do not establish learned benefit.

## Actual HTTP and browser observation

The production build was served with the real immutable WSGI artifact application.
Browser traffic was not intercepted or fulfilled by Playwright. Three completed
graphs were reviewed at both 1440 px and 390 px. Every graph has five pool models.

| Graph | Actual model rows | Selected | Cost-skipped | Outside horizon |
| --- | ---: | --- | --- | --- |
| Price order | 3 | middle | large, outside | none |
| Learned order | 4 | middle | outside | none |
| Shortened price horizon | 2 | none | none | middle, large, outside |

All six reviews verified the intended state and outer panel width. Mobile tables
scroll horizontally; their full width is not compressed into the viewport.
Screenshots were retained, and price/mobile and learned/desktop captures were
visually inspected. The recorded model, decision, report, plan, price table,
policy/training where applicable, and selected-design downloads all matched
original bytes: **74 downloads**, and **242 exact original HTTP responses**.
Server receipts confirm zero new solver calls and zero fits during this review.
Learned HTTP admission may recompute predictions with the existing policy; this
is not retraining or a fresh numerical path.

The summed review interval is **30.714068554 s**, including navigation,
validation, selections, downloads and a deliberate **250 ms interval before
each of 74 download clicks**. It excludes browser launch, server startup,
screenshots, teardown and earlier fixture generation/training. It is not a
solver speedup measurement, a full end-user cost or an unpaced latency benchmark.

The first observer failed at server import because the repository Python path
was not explicit. The second reached the price view and 42 exact HTTP responses,
then timed out waiting for a decision-download event. Both were terminal before
the next observation. Their sources and failure records are retained. Explicit
repository imports, action/console records and paced serial interactions were
used for the completed observation. The download timeout's cause is not proved;
the paced success does not establish reliability under an unpaced download burst.
The failed attempts' complete parent intervals are unknown and are not included
in the successful review interval.

## Observed viewer limitations

The RC review completed, but the embedded legacy viewer logged companion-data
404s, an unavailable preset sidecar, and `ReferenceError: initLog is not defined`,
followed by a demo fallback. The source call is in
`src/structure-viewer/index.html`'s workspace-preset error path. Drawing comparison
and catalog hydration also reported failures. The headless environment logged
software WebGL fallback and iframe-sandbox warnings. No unsafe browser flags were
enabled to suppress them. The recorded `page_errors: []` covers uncaught page
events only; it must not be described as an error-free console or a functioning
real-data legacy viewer. These are retained integration issues for follow-up,
not proof of full viewer, GPU or production readiness.

## Retained packets and remaining scope

All roots below are under
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/` and are read-only:

| Packet | Files / bytes | Inventory SHA-256 |
| --- | --- | --- |
| `structural-layout-pruned-workbench-8J5kej` | 13 / 1,081,875 | `102cd7dead5c743b8008599af871071339597633df0977175986f2619d93e57b` |
| Import failure `structural-layout-pruned-workbench-ekiplS` | 2 / 8,573 | `3e896d6480719466bf984d70c38dc8cfe5040ea4895ddebccfcd18b90a8c1a79` |
| Download timeout `structural-layout-pruned-workbench-C6DZiW` | 3 / 19,272 | `f45d64f41c30b5a32ffce9e6ca22d5dfa7ca6edf522389af39c5e30cbeb6e46a` |

See the [machine-readable observation](rc-layout-pruned-workbench-20260913.summary.json)
and [HTTP admission record](rc-layout-cost-pruned-http-20260913.md).
This completes the bounded cost-pruning report's RC panel connection. It does
not close multi-fidelity exploration, learned net benefit, independent project
or physical validation, broader material/3D support, full CI or the full roadmap.
