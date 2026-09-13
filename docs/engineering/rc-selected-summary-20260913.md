# Readable selected RC quantities and costs

Source `55b23b41410315eab1c2252502ee78e31016a84a` adds a responsive selected-candidate
summary above the wide original comparison. Mobile users can read gross concrete,
longitudinal rebar, declared material estimate, estimate change from baseline and
maximum path fiber strain without horizontal scrolling. Selecting another eligible
candidate updates the summary. It appears only for a selected row with full stored
reference verification, passing selection limits and declared prices; invalid,
unpriced and no-eligible-selection states show no summary.

Cards use six significant digits, with their exact source value retained in the
value's title attribute. The comparison tables and downloads retain original values.
The rounding scope is stated beside the cards. Positive estimate change means the
selected material estimate is higher than baseline, preventing a required more
expensive alternative from being described as a saving. No selection, price,
quantity, performance or numerical result is rewritten. Original model/result/price
identities and the existing explicit authority and material-scope limits remain.

The production build passed TypeScript, Vite and viewer-delivery checks. Twelve
browser regressions passed in 39.8 seconds using an explicitly started local static
server. They verify baseline-to-alternative updates, exact title values, rounded
values, viewport/card overflow, invalid/unpriced/strict-limit suppression, download
invalidation and existing exact original exports. A first attempt without the
server failed at connection; a later rounded-value assertion had an incorrect
fixture expectation (the original is 190.0626, rounded to 190.063), which was corrected.
These do not represent numerical failures or changed source prices.

A separate actual authenticated HTTP observation used the two newly generated
geometry graphs at widths 1440 and 390. All four views matched the five summary
source values and rounded displays, as well as the original quantity/cost table
and four performance fields. It checked 208 original HTTP responses, made no
new downloads, recorded no page exceptions and ran no solver or fit. The final
mobile screenshot was visually inspected and its cards need no horizontal scroll.
The original wide comparison tables still scroll on mobile.

The first summary observer assumed a direct-report delta field existed in the
layout graph and stopped on its expected-value mismatch. Its corrected fresh run
derives the expected delta from original selected and baseline estimates. The
product already used the verified layout display projection; no raw graph was
modified to satisfy the observer.

The [machine summary](rc-selected-summary-20260913.summary.json) retains the original
packet and source identities. The four final review intervals total 5.263390144 s,
excluding server startup, browser launch, screenshots and teardown. This is not a
paired performance experiment or a full user-flow speedup. Independent physics,
learned net benefit, hosted qualification and the complete roadmap remain open.

## Completed preceding-source CI

Source `0efd85afdfe33314c70fcfdc26802d81159e0bc0` completed development job
`103678943481` with **1,063 passed in 1,105.44 s**. Native PR Fast run
`34740368254` passed. Repository Python run `34740368308` failed: each of
its four full shards failed exact-source evidence materialization and skipped
pytest. The inspected shard-0 log retains `legal_approval=False`, product replay
not passed and technical receipt not ready. The [CI record](rc-selected-summary-20260913.ci.json)
binds source/job identities and downloaded log hashes. These results precede the
new geometry documentation and mobile summary code; they do not qualify the new
head. Publication waited for the development job to finish without cancellation.
