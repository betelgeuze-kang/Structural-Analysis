# Stored constant-load RC review in Workbench

Source `1e9e1fb29f14d92325e803c3ead36e5641e598de` extends the existing stored RC
Workbench reader and panel to the [v2 constant-load durable result](rc-constant-load-durable-20260910.md).
It uses original producer artifacts and retained worker verification. No structural
solve, learning fit or additional experimental-data admission occurs in this review.

## Stored identities and displayed physical state

The reader pairs v2 configuration, durable result/checkpoint, public API and native
restart schemas. It checks node-bound FX/FY/MZ constants, original preload-result
and assembly hashes, accepted preload ancestry, phase costs and each compact
receipt's preload identity. Native prefix preload and accepted bindings must match
the final cumulative restart. Rehashed preload response, epoch, work, source and
earlier-receipt alterations reject before physical rows are exposed.

The panel displays the constant nodal load table with kN/kN m units and an explicit
**Preload: constant loads** selection. Its response is epoch one, followed by lateral
epochs two through four in the retained fixture. The target list remains the three
prescribed lateral targets; preload is not counted as another prescribed target.
The selected preload includes node displacements, support reactions, member forces,
section results and material points. Concrete and steel histories include the
preload state and all later states. Existing proportional v1 behavior is retained.

Known core-call totals include all preload, prefix and suffix work from analysis
and fresh verification. The fixture shows **18 core calls**, **36 known Newton
iterations** and **six reserved API invocations**. These counts describe the original
worker computation, not browser work. Source revision remains explicitly a caller
declaration, and the browser does not assert independent numerical execution.

## Original HTTP fixture and validation

The new fixture is exported through the actual Python HTTP handler from a fresh
copy of the sealed `structural-constant-durable-cybslpqe/split/store`. The original
store is not reopened. Request, checkpoint, result and evidence match the sealed
source bytes exactly; the job view is the actual HTTP projection of the copied
completed job. Export performs no numerical calls.

| Original artifact | Bytes |
| --- | ---: |
| Job view | 1,714 |
| Request | 2,236 |
| Saved checkpoint | 24,349 |
| Result | 206,910 |
| Completion evidence | 2,385 |

The fixture's [inventory](../../tests/frontend/fixtures/rc-fiber-constant-durable-job/inventory.json)
retains SHA-256 identities and its README names the actual producer source and
sealed packet. It is an authored correctness fixture, not an independent experiment.

TypeScript, the production Vite build and viewer-delivery checks pass. The RC job
contract/browser selection passes **22 tests in 29.5 s**. Separate existing RC
design contracts pass **19 tests in 13.5 s**, covering the shared accepted-history
validator and quantity/price selection behavior. Earlier 9- and 16-test selections
overlap the 22 and are not additional coverage. The new constant tests are included
in the repository's Workbench E2E runner.

At **1440 by 1000** and **390 by 844**, the browser selects preload and all three
lateral responses, checks original reaction/displacement values, and verifies all
four material-state hashes for both steel and concrete. Each viewport downloads
five original artifacts, including the unchanged native terminal restart; all ten
downloads match their original bytes. Panel bounds stay within the viewport and
wide physical tables scroll locally. The two retained screenshots are visually
reviewed. Browser requests are routed to the original HTTP response bytes; this is
not a live production deployment or an independent user/device acceptance test.

The tested working tree is committed without code changes as the source above.
Fifteen changed/shared source and fixture files match that commit in the retained
snapshot. Built reader/Workbench assets, original HTTP fixtures, logs and screenshots
are retained in [the machine summary](rc-constant-load-workbench-20260910.summary.json)
and packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-workbench-sqjnl9uv`.
All test processes and their temporary server complete before sealing **32 files /
1,763,119 bytes**, inventory SHA-256
`ee2e5cdac0b51c6ed6e80d41201796e6b4c9e864877e350116430e45f7bc6fd9`.
Build chunk-size and experimental-loader warnings remain visible in the log.

This completes stored v2 constant-load job review for the existing bounded profile.
The 255-target limit, full experimental loading-history reconstruction, execution-
topology buffers, constant-load design-study/learning admission, independent physical
validation, source reuse decisions and hosted/full-roadmap acceptance remain open.
No protected receipt, tolerance or release authority is changed.
