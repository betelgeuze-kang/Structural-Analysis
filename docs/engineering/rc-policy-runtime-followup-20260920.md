# Full-path selection with exact-content policy parse reuse

The [proposal-stage result](rc-inference-policy-reuse-20260920.md) is being
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

No final score or selection is available at this record. The completed scalar
study remains negative for learned acceleration (ratios 1.015901 and 1.026031).
Audit the final roster, group exclusions, physical comparisons, costs and source
bindings using `audit_rc_pooled_runtime_campaign.py`; then require the separate
full numerical-equivalence audit. Archived sources and numerical inputs remain
unchanged during measurement. This experiment does not supply independent
physical validation, reserved evaluation, policy promotion or roadmap closure.
