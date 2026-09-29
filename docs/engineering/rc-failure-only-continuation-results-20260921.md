# Failure-only continuation trades easy-path savings for failed-first cost

Frozen source `1741221ac87752382ea9df16b5fc2d7ce9320227` completes the fixed twenty comparison executions / eighty attempted paths. All twenty proposal paths finish. Forty-four paths in total finish; the other thirty-six ordinary/secant/fresh-reference paths at 40 mm remain incomplete. Every complete proposal history agrees between upfront and failure-only continuation within the existing 1e-10 absolute / 1e-8 relative comparison limits in both orders.

| Model/history case | Failure-only / upfront proposal path time, ratio of two-order sums | Additional proposal calls, upfront → failure-only | Fresh ordinary-reference comparison |
| --- | ---: | ---: | --- |
| w32 cheap, 20 mm | 0.374324 | 32 → 0 | both modes pass |
| w48 cheap, 20 mm | 0.379007 | 32 → 0 | both modes pass |
| w32 cheap, 40 mm | 1.329157 | 32 → 32 | both modes fail |
| w32 middle, 40 mm | 1.229942 | 32 → 32 | both modes fail |
| w48 cheap, 40 mm | 1.214603 | 32 → 32 | both modes fail |

Thus waiting for actual failure removes needless sixteen-stage searches on the two cases ordinary Newton can solve. Their observed enclosing proposal path time falls 62.1–62.6% relative to the always-on internal continuation strategy. This is not acceleration relative to secant, learned acceleration or end-user workflow savings. On the three difficult cases, attempting ordinary Newton first adds observed cost of 21.5–32.9% relative to upfront continuation. Those comparisons involve two completed proposal strategies, but no completed ordinary reference is available, so they cannot qualify a reference speedup or independent physical agreement.

The roster contains five model/history combinations, not five independent physical experiments or projects. It reuses three model configurations at two amplitudes. Two balanced observations per mode do not establish a broad statistical timing distribution, optimal switching classifier or production policy. Both modes remain explicit experimental options; ordinary defaults are unchanged.

All failed attempts remain accounted for: 346 ordinary path native calls plus 256 internal proposal calls = 602 native calls; 1,912 ordinary plus 786 additional Newton iterations = 2,698. The successful ordinary cases perform zero internal proposal solves in failure-only mode. The difficult cases preserve each failed initial invocation, exact rollback and subsequent candidate acceptance; an interrupted search stops with unknown work instead of issuing another reference attempt.

The audit verifies all twenty report/path hashes, stage artifact hashes/lengths and parent bindings, known-work totals, complete roster and ten paired full-history comparisons. All 3,721 inventoried non-cache files were reread. Inventory SHA-256: `1153e03abe4cdf9bf7361df5ccaaeae13136b96e182d625341c5319ff25b60ba`. The [summary](rc-failure-only-continuation-results-20260921.summary.json) includes individual summed clocks and reference gates.

Verification comprises 93 warm-start/parent/observation regressions, twenty strategy/replay tests after adding interruption accounting, and a subsequent actual parent-step budget regression. The parent-step declared maximum now includes all sixteen internal proposal calls (22 rather than 6 for the tested four-arm bound). Ruff and diff checks pass. Initial exclusive-file failures were resolved by preserving the initial proposal artifact and writing a separate continuation outcome, not by permitting overwrite.

The useful next decision is when to pay for continuation. A learned predictor would need independent model/history splits and full-cost comparison against this deterministic failure-triggered baseline; the present five combinations do not supply that evidence. Broader physical validation, public product admission and release dependencies remain open.
