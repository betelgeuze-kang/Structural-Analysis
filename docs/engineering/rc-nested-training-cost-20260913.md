# Historical training interval containment

The standalone strategy and enclosing process comparators now reject historical
training clocks that exclude their own recorded sequential analysis/replay work.
Previously, a controlled mutation retained 2,695,884,138 ns of child wall intervals
but zeroed the generation, fit and total wall clocks. After rebinding the report
and plan hashes, accounting accepted zero historical training cost instead of the
original 2,715,988,518 ns. This was metadata mutation, not a new speed experiment.

The consumer validates each child wall/CPU clock as a nonnegative safe integer,
requires returned analysis/verification pairs, and checks that their wall sum fits
inside label generation. Generation plus fit must fit inside total wall time;
child CPU plus fit CPU must fit inside total CPU. Parent and child intervals are
never added twice. Historical report deduplication and unequal-outcome null ratios
remain unchanged. These checks establish internal consistency, not clock
attestation: consistently forged clocks still require trusted original evidence.

The strategy/process suite passes 46 tests, including rehashed missing-cost,
invalid-clock and incomplete-phase regressions. The original eight executions
from the standalone strategy packet were re-read against their inventory and
recounted with the new consumer. Both complete accounting objects are unchanged:
the four-pair ratio stays null and the comparable budget-11 stratum remains
1.126194047742893 after training. No solver, fit or physical replay was run.

The adjacent JSON records the reproduction and retained packet. This change
supports full-cost integrity; it does not establish learned net savings, external
physics, new-head hosted qualification or roadmap completion.

## Workbench consumer consistency

The Workbench candidate, standalone cohort/process and layout search consumers
now apply the same sequential child-interval containment rule. The process-cost
panel was already connected; this follow-up fixes its upstream input validation.
A shared validator checks returned analysis/verification phases, safe child clocks,
wall containment in generation/total, and CPU containment including fit.

Before the fix, five deliberately mutated training records still passed the
complete candidate-search consumer after all training, plan and report hashes
were recomputed and independently checked. They erased parent wall/CPU costs,
changed a verification to analysis, marked an invocation raised, or used a boolean
child clock. All now reject. Two additional layout parent-cost regressions reject
through the same public review entry point.

The final candidate/cohort/layout selection passes 141 contract tests in 24.8 s;
TypeScript and diff checks pass. This invokes the real frontend validators on
retained source artifacts, not a new browser-rendering or numerical campaign.
The earlier candidate/cohort-only selection passed 76 tests before the helper was
shared with layouts. The adjacent `rc-workbench-training-cost-20260913.json`
records the retained source/log packet. Normal original comparisons remain valid;
no new timing result, external validation or learned gain is claimed.
