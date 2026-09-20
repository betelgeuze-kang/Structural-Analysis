# Immutable policy parse reuse during learned proposals

`RCControlSeedPolicy.propose` now reuses a recursively immutable parsed policy
keyed by its exact JSON text, bounded to four cached policies. Different JSON
content cannot reuse an old entry. The constructor still performs full strict
policy validation, public `to_dict()` still returns independently mutable data,
and every proposal still validates the current material snapshot and source.
Only fixed model/DOF/material-name comparisons use tuple equivalents internally;
weights, scaling, arithmetic and abstention rules are unchanged. No accepted
state, dynamic feature or prediction is cached.

Verification uses the sealed 90-fold scalar-runtime packet. The original proposal
method is extracted from committed `cef10ca63` source and compared with the new
method on **all 1,080 original contexts**. Results match exactly, including 486
raw-policy abstentions and all 594 recorded seven-coordinate proposals. Mutating
a freshly returned policy dictionary does not change any of those predictions.
These are retained-context checks, not new accepted full paths.

Actual learning/split regression tests pass **69 tests in 116.52 seconds**.
A new test verifies recursive immutability, content separation and eviction at
four entries. Lint and whitespace checks pass.

Six alternating old/new measurements use the same D-amp100 target-6 context,
100 proposals per arm, and clear the parse cache before every arm. Each new arm
records exactly one cache miss and 99 hits, so cold parse/preparation cost is
included. New/old time ratios are 0.56966, 0.57121, 0.57135, 0.57188, 0.57242 and
0.56403: roughly 43% less proposal time in this observation. All coordinates
match the original recorded proposal. No solve or fit is executed by these
measurements; this is not whole-path acceleration or independent generalization.

The [machine summary](rc-inference-policy-reuse-20260920.summary.json) records
raw timings, correctness counts, parent source revision and the packet inventory.
The packet retains the exact edited source, patch and reproduction scripts.
The measurement script expects the preserved check script at its original
`/tmp/check_rc_inference_reuse.py` path when reproduced. Complete-path comparison
must include cold preparation, eviction, reference verification and all remaining
material capture cost before revising the current secant selection. No new
policy is fitted or promoted, and all roadmap closure requirements remain open.
