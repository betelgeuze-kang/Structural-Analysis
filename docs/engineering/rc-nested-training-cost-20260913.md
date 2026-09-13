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
