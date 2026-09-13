# Why fewer recorded linear solves did not ensure cheaper paths

Two read-only diagnostics decompose the sealed
[full quadratic screening](rc-quadratic-full-20260914.md). No numerical paths,
labels or fits were added. Eight original secant/proposal paths were authenticated
against the sealed inventory; 1,936 original step records were then authenticated
and passed `summarize_rc_control_iteration_cost`. Recorded step counts agree with
the assembly dispatch phases and inclusive invocation counts.

| Case | Primary rows delta | Line-search assemblies delta | Terminal linear solves delta | Terminal assemblies delta | Total linear delta | Total assembly delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train-a | -7 | -7 | -5 | -1 | -12 | -15 |
| train-b | +10 | +10 | -17 | +2 | -7 | +22 |
| train-c | -22 | -22 | +3 | +3 | -19 | -41 |
| train-d | +6 | +6 | -14 | 0 | -8 | +12 |

Deltas are proposal minus secant. Final-observation assemblies remain 242 per
path. In these records, inclusive linear solves equal primary convergence rows
plus terminal-refinement linear solves; the diagnostic verifies that identity
against each original step rather than inferring it from wall time.

In train-b/d, fewer terminal linear solves outweigh *more* primary rows in the
inclusive count. Primary assembly and line-search work both increase. Thus the
earlier statement that linear work fell in all four cases is true but insufficient
to show improved primary convergence. The arithmetic explains the apparently
conflicting work counts. There are no phase-specific durations, so it does not
quantify which phase caused the observed wall-time change.

The paths have independent evolving native states. Matching target indices do
not establish identical parent checkpoints; per-step differences must not become
same-parent counterfactual labels for a learned router. Even target 23 in train-b,
where linear work falls and assembly work rises within the matched target pair,
does not change that limitation. These are previously inspected related training
cases, with no independent generalization evidence.

The next policy comparison should keep primary convergence, terminal work,
assembly work and full elapsed cost separate. Using inclusive iteration or
linear-solve count alone as a reward could prefer an initial estimate that worsens
primary convergence. No terminal refinement or physical acceptance check should
be removed merely to improve that score. Neither a gate nor a learned model is
adopted from this retrospective decomposition.

## Original evidence

The [phase receipt](rc-quadratic-assembly-phases-20260914.json) retains an eight-path
phase aggregation, 968 paired target rows and source bindings. Its sealed packet
contains two files / 290,941 bytes; validation and aggregation take 0.900338737 s.
The [terminal-work receipt](rc-quadratic-terminal-work-20260914.json) cross-checks
all 1,936 original steps, including terminal attempts, accepted corrections,
linear solves and assemblies. Its three-file / 1,085,757-byte sealed packet
contains the profiler, exact cost-summary helper and per-step rows/bindings.
Validation and aggregation take 15.400538822 s. These intervals exclude final
packet writing/readback/sealing and are separate from the numerical experiment.
Both inventories were reread and checked. Full roadmap closure remains open.

## Reusable execution-report summary

Opted-in `record_assembly_work=True` reports now include `assembly_phase_work`
for reference, secant, proposal and fresh reference. The summary authenticates
each path's internal hash, validates recorded dispatch order/totals, and counts
preload and attempted-step invocations. Missing or in-flight dispatch records
retain observed partial counts but have null complete phase/dispatch totals.
Raised calls remain counted with an explicit failure count; failed paths do not
become successful merely because their work is known. Line-search reuse hits
remain separate from actual dispatches. Per-phase durations, work outside Newton
and physical/source-file authority remain unavailable or false.

The report separately records `assembly_phase_summary_wall_ns` and includes it
in the whole-study wall/CPU intervals. This performs additional path validation
only when recording is explicitly enabled. The default execution and numerical
algorithm remain unchanged; no runtime selector or reward is switched to these
counts alone.

Thirty-nine focused tests pass in 29.84 s, covering actual paths with/without
constant preload, ordinary/retained arithmetic, exact step-byte preservation,
single-parent runs, missing/in-flight/raised records, inconsistent counts and
reuse separation. Ruff and diff checks pass. The new summarizer also reads all
16 authenticated original full-screening paths and reproduces the earlier audit's
invocation/assembly totals, with zero new solves or fits in that separate check.
These local checks do not qualify the complete repository suite or external
physical accuracy.
