# Completed full-path selection with exact-content policy parse reuse

The [proposal-stage result](rc-inference-policy-reuse-20260920.md) was
followed by the same complete pooled selection at frozen source
`7a41a1566a605ed1529563619cbc70dbbd0eef17`. Among files shared with the prior
85af596ed numerical archive, only `rc_control_learning.py` changes. Source files
are copied from Git blobs with individual lengths and SHA-256 hashes.

Preflight passes with 17 declared cases, 165 original training samples and five
whole geometry/history exclusion groups; no preflight solve or fit occurs. The
unchanged driver schedules 90 comparisons and 360 full paths, two ridge values,
three counterbalanced repetitions, 132 complementary samples per fit, the 1%
minimum improvement rule, static abstention and secant fallback. Original
acceptance tolerances, all material checks and reserved-case exclusion remain.

The launcher asserts an empty inference cache in a fresh process and records
that state before calling the original driver. The first parse occurs inside
the actual proposal call and its timed path. The four-entry cache is not cleared
between repeats or identical policies. End-of-process hit/miss/size counts are
recorded separately. This represents bounded reuse in one study process, not
cold startup for every independent path. The enclosing process time includes
the launch and cache receipt handling. No excluded warmup run is performed.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-policy-runtime-q8fxqvd8`.
The original process was started as PID **234414**, observed through shell
session **87000**. Preserve it until authoritative termination; do not restart
on an observation timeout. `process-started.json` and `inference-cache-start.json`
record the launch. Terminal process and cache receipts will follow completion.

At the original live observation, no final score or selection was available. The completed scalar
study remains negative for learned acceleration (ratios 1.015901 and 1.026031).
Audit the final roster, group exclusions, physical comparisons, costs and source
bindings using `audit_rc_pooled_runtime_campaign.py`; then require the separate
full numerical-equivalence audit. Archived sources and numerical inputs remain
unchanged during measurement. This experiment does not supply independent
physical validation, reserved evaluation, policy promotion or roadmap closure.

## Cache lifecycle auditor prepared during execution

`scripts/audit_rc_policy_cache_receipt.py` reconstructs the exact-content
four-entry LRU access sequence from all 90 completed fold policies and model
gates. It requires a zero-hit/zero-miss/empty initial cache, exact nonnegative
integer counters, no between-fold clearing, complete proposal paths and bound
policy/report/gate hashes. Observed terminal counters must equal the reconstructed
hits, misses and final size. Static-gate bypasses are counted separately.

Eleven focused cost/accounting tests pass, including hot-start, boolean counter,
wrong-hit and lifecycle rejection plus exact-content and eviction checks. This
adds no fitting or numerical execution. The full cache audit cannot run until
the original process writes its terminal cache receipt; it supplements the
existing full runtime and numerical-equivalence audits.


## Completed and audited: no overall learned benefit

The original process exits successfully. Full runtime, numerical-equivalence and
cache-lifecycle audits all pass without another solve or fit. All 90 comparisons
and 360 paths pass their original checks, with 594 proposals, 486 abstentions,
4,680 core calls and 24,054 Newton iterations/linear solves. Every fit excludes
its entire geometry/history group and retains the same 132 complementary samples.

| Ridge | Equal-case learned/secant mean time ratio | Decision |
| --- | ---: | --- |
| 10,000 | 1.0119626435127704 | Rejected |
| 1,000,000 | 1.0217371315277548 | Rejected |

**Secant remains selected.** Neither candidate meets the unchanged 1% minimum
benefit rule. No winning-policy refit, promotion or reserved evaluation occurs.

One active-proposal case, D-amp150 with ridge 10,000, is faster in all three
repetitions: ratios 0.9861880468, 0.9956813338 and 0.9893517854, with mean
0.9904070553 (about 0.96% shorter). That case mean does not meet the 1% rule,
and selecting it after observing this study would not constitute a validated
causal selector or independent generalization. The other four consistently
faster cases have zero proposals and therefore cannot establish an AI gain.

All **4,680 step files, 360 preload responses and 4,320 input contexts** match the
original pooled study bytes exactly. Original model/request/numerical contracts
and frozen policy identities agree. Cache accounting reconstructs exactly **648
inference calls: six misses and 642 hits**, ending at four entries. Static gates
bypass 432 calls. The process starts empty; repeated paths do not each start cold.
All initial parsing occurs within actual proposal calls and their timing.

Selection wall time is 1,500.444965252 seconds, enclosing driver time
1,501.232796913 seconds, and outer process time 1,502.638097327 seconds. These
nested intervals are not added. Thirty selection fits total 0.703045686 seconds;
the separate pooled metadata fit takes 0.026007452 seconds. Historical label
costs remain separately preserved. Cross-run changes in total time or candidate
scores are not controlled causal speedup evidence.

The [machine summary](rc-policy-runtime-followup-20260920.summary.json) includes
all repeat scores, costs, three audit outcomes, source identities and final
packet inventory. The prior live observations remain historical records.
The implementation reduces repeated policy preparation and preserves numerical
results here, but does not close the useful learned-acceleration requirement.
Further work should use these preserved failures and the narrowly favorable D
case to define a cost-aligned experiment, without treating divergent-path step
pairs as same-parent training labels or promoting a post-hoc case filter.
All five roadmap goals and independent verification requirements remain open.
