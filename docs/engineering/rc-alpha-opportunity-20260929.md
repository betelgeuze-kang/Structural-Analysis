# Prospective RC line-search work screen on three harder synthetic histories

The [earlier A–E trace screen](rc-line-search-alpha-feasibility-20260929.md)
found only three first-alpha failures among 373 primary Newton line searches,
all in one geometry/history group. This follow-up fixed three new training-only
L-frame cases before solving. It asks whether larger reversing drifts create
enough failed alpha trials for a future learned skip policy to save actual
assembly work. No policy was fitted, used, or promoted.

The exact clean producer was `e5011c08f1088acf351133936dcbd1220f9f5761`
on local `codex/rc-alpha-opportunity-20260929`, stacked on draft PR #509.
The three authored cases H/I/J have 2.45/2.05, 3.15/2.55, and 3.65/2.95 m
horizontal/vertical member lengths. Their twelve control targets reach
12.0, 14.4, and 16.8 mm in the first negative excursion. Each uses the
same public example template, 20 kN constant vertical preload, retained
twofold arithmetic, terminal polishing, and the fixed alpha grid
`1, 1/2, …, 1/4096`. Whole-group geometry/history declarations are distinct
within the three cases. All come from one authored template, so their IDs do
not establish independent projects or physical validation. No reserved case
or external measurement source was opened.

The producer ran reference, optimized secant with immediate line-search
assembly reuse, and fresh reference from genesis for each case. It timed
assembly dispatches and retained all original step, context, outcome, path,
comparison and started files. Its opportunity extractor requires a complete
path, exact one-invocation target roster, known work, passing full response
history against fresh reference, and a trial-to-assembly count match before
giving an eligible count. Incomplete or retried paths remain in the declared
three-case denominator without a favorable count.

| Case | Complete paths | Target searches / trials | Target assembly wall | Preload searches / trials | Preload assembly wall | Whole secant searches / trials | Whole line-search assembly wall | Secant path wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H | 3/3 | 39 / 39 | 0.912068 s | 1 / 1 | 0.022682 s | 40 / 40 | 0.934750 s | 3.364665 s |
| I | 3/3 | 35 / 35 | 0.875668 s | 1 / 1 | 0.021586 s | 36 / 36 | 0.897254 s | 3.335762 s |
| J | 3/3 | 34 / 34 | 0.808925 s | 1 / 1 | 0.023030 s | 35 / 35 | 0.831955 s | 3.336591 s |
| Total | 9/9 | **108 / 108** | **2.596661 s** | **3 / 3** | **0.067297 s** | **111 / 111** | **2.663958 s** | 10.037017 s |

The target-control rows and constant-preload rows are disjoint. Every one of
the **108 target** and **3 preload** first-alpha trials succeeded; neither
scope has a failed trial. The original whole-path phase timer includes both
scopes: 2,596,661,045 ns target assembly plus 67,297,177 ns preload assembly
equals 2,663,958,222 ns whole-path line-search assembly. There is therefore
zero measured rejected-trial dispatch time to omit on these particular paths.
The whole-path assembly time is for the **accepted** trials; it is not
available as a skip saving.
No counterfactual skipped-alpha trajectory was run. The result is a negative
opportunity screen for this proposed learning target on these cases, not a
speedup comparison or a general bound on other models.

The separately committed read-only auditor recomputed the plan/outcome and
report/path hashes, the original reference/fresh full histories, every secant
trial and its measured dispatch, and a byte inventory of all **737 files**
totalling **40,181,128 bytes**. The inventory digest is
`5d6bdbec7776370a07bd88b850a012ba6356feccbd8df0124aa489b1bfd72bad`.
The original packet is machine-local at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-alpha-opportunity-20260929-e5011c`.
Its plan and outcome file SHA-256 values are
`a3a0fbf6b92b8add583eeebdf8d108b8f6b81eb8081f2e98ad889fb4e76233da`
and `11a2cf1f18b34a877d675bc42ae1fc986c4daa20acecb202bc1531b2f1611202`.
The [small machine summary](rc-alpha-opportunity-20260929.summary.json) keeps
target, preload, and whole-path scopes separately for each case, plus exact
report hashes; the 40 MB original is not in Git.

Focused alpha extraction/accounting tests: **27 passed**. Ruff check and
format checks pass. To reproduce from the producer commit, run the producer
with `PYTHONPATH=scripts:src`, an empty output directory path on `/mnt`, and
single-threaded BLAS settings. Run
`scripts/audit_rc_alpha_opportunity_campaign.py --packet <output>` on the
resulting original packet. The committed audit pins this particular run's
plan, outcome and inventory digests, so a fresh run needs its own receipt
and auditor pinning rather than inheriting this result.

A post-run parser correction counts every rejected trial when a line search
has no accepted alpha. All three original paths have zero such rows, so the
read-only audit still reproduces the exact frozen plan, outcome and packet
inventory. The producer revision above remains the numerical source; this
later parser correction did not rerun or alter a structural path.

A subsequent post-run scope correction separates target-control and preload
trial counts and timed assembly in the read-only audit and derived machine
summary. Previously the target-only 108-search count appeared next to the
whole-path 2.663958 s assembly time, which also contained three preload
searches. This correction verified the disjoint sums against the unchanged
whole-path phase timers and original packet inventory. It did **not** execute
another structural solve, change the `e5011c08` numerical producer, modify
the original packet, or measure a new policy outcome.
The current runner's package/CLI import compatibility adjustment only lets
the same audit helpers load under standard test collection; it does not
change the frozen producer's numerical algorithm or this packet.

The prior A–E and new H–J observations have different exact source revisions
and are reported separately. Neither supplied cross-group evidence for an
alpha-skipping learner. The next useful experiment would first identify a
source-bound *training* corpus with repeated backtracking in several whole
geometry/history groups, then freeze a causal rule and measure new complete
paths including feature extraction, inference, retries, recovery, verification
and training costs against optimized secant. Solver acceptance remains
authoritative. This run leaves held-out evaluation, independent physical
validation and learned net savings open.
