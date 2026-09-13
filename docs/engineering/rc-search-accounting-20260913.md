# Direct-control candidate search interval accounting

The new `structural_analysis.benchmark.rc_control_search_accounting` module
audits arithmetic across original v3 direct-control search reports. It keeps
price-arm execution, learned-arm execution, learned prediction/ranking, the later
exhaustive oracle and unallocated preparation/I/O intervals separate. Each arm's
recorded interval already includes its fresh full-path verification; that work
must not be added again. Training label and fit intervals are components of
the historical training total, not additional charges.

Distinct search reports sharing exactly the same hash-bound training report
charge that historical total once. Different training reports remain separate,
even when their times coincide. Repeating the same search report is rejected;
it cannot masquerade as a second observation. This identity rule is scoped to
training artifacts, not proof of ownership or cross-campaign provenance.

The command accepts one or more original reports and writes a separate JSON
accounting result to stdout:

```sh
PYTHONPATH=src python3 -m structural_analysis.benchmark.rc_control_search_accounting \
  /absolute/path/to/search-1/result.json /absolute/path/to/search-2/result.json
```

Inputs use the bounded strict JSON parser. Both outer search and nested training
hashes are checked. Unknown timing scopes, unfinished arms/fits, negative or
non-integer clocks, duplicate execution reports and nested intervals exceeding
their containing interval reject. The command performs no solver calls or fits
and never modifies inputs. Hash and arithmetic checks do not independently
validate the reports' numerical assertions or external authority.

## Existing original-data observation

All six search report files in the sealed cheaper-boundary experiment were
reread and matched to their existing byte-length/SHA-256 inventory entries.
The inventory itself matches the previously documented digest. The unchanged
reports pass the new accounting audit:

| Recorded scope | Seconds |
| --- | ---: |
| Six search intervals, including both arms and any oracle | 49.638670883 |
| One shared historical training interval | 2.761753795 |
| Sum of these recorded intervals | 52.400424678 |
| Unallocated preparation/I/O within those search intervals | 0.153522629 |

The last row is already included in the first row. The sum is not the elapsed
time of a new campaign. Historical searches and training happened previously;
this arithmetic audit performs no numerical rerun. Final search report writing,
source preparation, separate external audits, transport and Workbench review
are outside these input intervals and remain explicitly excluded/unmeasured
by this tool. The prior experiment's separate parent and browser observations
must not be replaced by this narrower sum.

The producer has no separately measured complete preparation/delivery interval
for each deployed strategy. Therefore the audit emits no net-speed ratio or
break-even projection, and retains `net_savings_proved=false`. Unallocated
costs are not silently assigned away. The next runtime experiment must meter
complete strategy paths separately and retain equal-quality selection checks
before making a total-cost comparison.

Fourteen focused arithmetic/strict-input tests pass. Two real small search tests
also exercise the audit with assembly reuse disabled and enabled, including
the exhaustive oracle and fresh verifications. Workflow contract tests require
the new test module in the development job (27 modules); full evidence gates
remain unchanged. These local checks do not establish hosted CI completion,
independent physical validation or learned net benefit.

The [machine summary](rc-search-accounting-20260913.summary.json) preserves all
six input identities, original inventory digest, accounting source hash,
per-execution intervals and the deduplicated training record. The sealed
original packet remains unchanged.
