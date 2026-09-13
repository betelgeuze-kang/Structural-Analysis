# Content-keyed RC section identity reuse

Implementation: `ce26ae36acd4c9611511cf02ddc9c8a6c67bbc64`.
A profile of the public extended sparse portal found repeated section-contract
canonicalization inside state and receipt validation. The profiled call made
13,230 base section hash requests, with 2.780 seconds inclusive profile time.
Instrumentation changes execution cost; that value is diagnostic, not a speedup
measurement or a disjoint share to add to other cumulative profile entries.

## Change and invariants

`StatefulRCFiberSection._base_contract_hash()` still captures current fiber and
material content on every request. A bounded 128-entry cache reuses canonical
hashing of the same immutable JSON snapshot. The key is not a section ID or
object address. Replaced materials, changed geometry and forced nested mutation
therefore change the key and continue to invalidate incompatible parent states.

The original canonical encoder computes every miss. Non-scalar or non-JSON
payloads take the original path, preserving supported types and rejection of
non-string object keys. Solver arithmetic, constitutive updates, convergence
thresholds, checkpoint checks and accepted-result authority are unchanged. This
cache is not a cached validation outcome or permission to skip a required check.

Focused section, stable-stress and sparse-factorization tests: **37 passed in
6.78 seconds**. New tests exercise changed material/geometry with the same ID,
forced nested mutation/restoration, and malformed nested mapping rejection.
Ruff, formatting, mypy for the changed module and diff checks passed.

## Matched actual executions

The experiment freezes 458 source files for each version. The baseline snapshot
is from `acd586e54aef44cd39cfa82fbc181fcfa6cf7ee2`; all package source content also
matches the pre-change source inspected at `c74f55326134d5195d900f61e6346875853596d9`.
Only `materials/stateful_fiber_section.py` differs between the two frozen packages.
Two related generated portal inputs use the previous 10x and 20x nodal loads,
with concrete tensile damage. No new independent structural family is claimed.

For each input and dense/extended-sparse backend, two fresh-process orderings
(before→after and after→before) run four unchanged load steps. All **16 runs / 64
committed steps** converge. All **8 before/after pairs** have byte-identical full
public result JSON and checkpoint bytes. No failure was removed from the schedule.
The audit checks both source snapshots and compares retained result bytes; it does
not rerun Newton or supply external physical validation.

| Input | Backend | API after/before sum ratio | Process after/before sum ratio |
| --- | --- | ---: | ---: |
| 10x | dense | 0.921172 | 0.960671 |
| 10x | extended sparse | 0.949989 | 0.967001 |
| 20x | dense | 0.913291 | 0.948410 |
| 20x | extended sparse | 0.939183 | 0.950939 |

Ratios divide the two after-run time sums by the matched two before-run sums.
API time includes existing internal source validation. Process time also includes
startup/import, model parsing, result/checkpoint serialization and exit. Source
copying, protocol preparation, the separate audit, browser delivery and explicit
history export are excluded. Single-thread environment and Haswell OpenBLAS core
selection are identical. This local sample shows roughly 5.0–8.7% lower API time
and 3.3–5.2% lower process time; it is not a confidence interval, larger-building
scaling claim or AI benefit. Extended sparse remains slower than dense here.

## Originals and open gates

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-section-cache-5n8m9tgs`.
`inventory.json` SHA-256:
`2d9c4afe626b72f6a1ad207a666a77cc18caab6ec29cf98f1e94879eb3e4a6ee`.
It covers 1,007 files / 20,636,417 bytes excluding the inventory, including source
snapshots, protocol, drivers, original outputs, audit and preceding profile.
The adjacent JSON summary preserves unrounded times and all eight pairs.

The preceding c74f55326 Repository Python run `34725854133` was observed running;
this is not a completed current-head full-suite result. The known external
reference precision discrepancy is not resolved by this change. Independent
validation, learned net benefit and full roadmap acceptance remain open.
