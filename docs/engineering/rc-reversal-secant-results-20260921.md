# Whole-path secant probe does not resolve the failed reversal

The fixed three-model, two-order probe completed six comparison executions and eighteen attempted full paths on frozen `ca07bb1ea`. Every reference, secant and fresh-reference path accepts -20 and -40 mm but remains incomplete at the +20 mm reversal. Both orderings give the same completion outcome for each model. There is no qualified speed ratio and no production policy change.

All eighteen paths preserve their attempted work. The six secant paths each retain one additional fallback attempt with the reference start; these also fail. The complete record accounts for 78 numerical core calls and 498 Newton iterations/linear solves, with no unknown invocation work. This includes all failures and the fresh-reference executions; it is not a successful convergence benchmark.

Original targets, loads, materials, tolerance and line-search settings were unchanged. No learned proposal, new training sample or hidden target subdivision was used. Existing full-history comparisons correctly fail because complete reference and candidate paths are unavailable. Partial-history numerical agreement cannot qualify an incomplete path.

The audit verifies all six report hashes, the complete roster, completion state and known-work totals. All 516 packet files were inventoried and reread. Inventory SHA-256: `b4d6ab74c7d45dc9149df548bcd5b4367ef85c6e28246fb49de0442fe0509787`. [The summary](rc-reversal-secant-results-20260921.summary.json) retains source/packet identities, clocks, comparison records and aggregate work.

Together with the fixed alpha-grid and retained-direction probes, this rules out the tested simple start/grid extensions as solutions for these three models. It does not prove physical instability, nonexistence of equilibrium or failure of other globalization methods. A subsequent solver development should investigate the nonlinear direction and material-branch traversal with bounded work, preserving the same original failure records and acceptance gates.
