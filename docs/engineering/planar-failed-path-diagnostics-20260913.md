# Retained diagnostics for blocked public planar paths

The failed 40x and 60x cases in the yielded-backend screen returned a solver
failure reason but no public convergence history. That absence must not be
interpreted as zero computation. Those sealed observations remain unchanged.

The blocked corotational public result now includes `metrics.observed_load_path`.
It reports attempted and committed steps, replayed prefix and newly attempted
steps, and recorded convergence-history rows. Each observed step retains its
target, commit disposition, terminal reason and exact failed-step rollback check.
The returned path includes any successfully replayed restart prefix.

This is diagnostic data, not complete cost accounting. History rows do not count
all linear solves, line-search assemblies, compilation or recovery work.
`total_api_work_accounted` is false. If no execution object is returned, the
observation is null; exceptions can occur after some work, so null is not zero.
Accepted numerical rows, checkpoint availability and engineering authority remain
unavailable on blocked results. Successful result serialization is unchanged.

Four actual public portal regressions cover dense and sparse CPU backends, each
with a one-iteration cap and with 40x generated nodal loads at the usual 40-iteration
cap. The former retain zero committed steps; the latter retain positive committed
step counts before failure. Both preserve positive history-row counts and
byte-exact rollback to the failed step's parent. The tests compare against the
captured real execution and run the public result validator. A rejected restart
retains a null observation. The 40x regressions are new functional tests, not
replacements for the previous sealed experiment or performance measurements.

The public sparse integration module passed 31 tests in 25.30 seconds. Ruff passed
for both changed Python files. Extended sparse integration and history comparison
passed another 130 tests in 205.64 seconds, including the actual 258-equation
public solve and prefix restart. These checks establish the bounded diagnostic
contract; they are not external physical validation, AI speedup, full-repository
qualification or a re-execution of the sealed yielded-backend screen.
