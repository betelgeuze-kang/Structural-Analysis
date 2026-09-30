# Full-layout strategy CLI and completed installation replay — 2026-09-13

A command-line entry now exposes the existing full-layout strategy APIs. It accepts
an explicit `price_order` or `learned_order` strategy and explicit `full`,
`cost-pruned` or `staged` execution. It invokes one strategy without an exhaustive
oracle. It does not change the solver, acceptance checks, consideration budget or
existing versioned result formats consumed by HTTP admission and Workbench.

## Input and execution

```sh
PYTHONPATH=src python3 -m structural_analysis.benchmark.rc_control_layout_strategy_cli \
  --model inputs/baseline.json --request inputs/request.json \
  --experiment inputs/layout-experiment.json --output new-result-directory \
  --source-revision FULL_40_CHARACTER_COMMIT_SHA \
  --strategy price_order --execution staged --prefix-target-count 2 \
  --full-analysis-budget 3
```

The experiment format is:

```json
{
  "schema_version": "rc-control-layout-experiment.v1",
  "candidates": [
    {"candidate_id": "small", "model_path": "small.json"},
    {"candidate_id": "large", "model_path": "large.json"}
  ],
  "prices": {
    "concrete_per_m3": 100,
    "rebar_per_kg": 1,
    "currency": "KRW",
    "as_of": "2026-09-13",
    "source": "synthetic development example only"
  },
  "history_limits": {
    "maximum_translation_m": 1,
    "maximum_absolute_fiber_strain": 0.000002
  },
  "material_limits": {
    "maximum_steel_accumulated_plastic_strain": 1,
    "maximum_concrete_tensile_damage": 1,
    "maximum_concrete_compressive_damage": 1
  },
  "terminal_limits": null
}
```

The displayed values are illustrative, not validated design limits or a quotation.
Use the existing complete RC direct-control request schema. Candidate files contain
complete canonical/neutral models, with one to sixteen alternatives. Paths are JSON
files relative to the experiment directory; absolute paths, traversal and escaping
symlinks are rejected. Duplicate JSON fields and extra experiment fields are rejected.
Existing engine preflight also rejects duplicate candidate/model identities, invalid
limits/prices, source revisions, improper prefix lengths and insufficient budgets
before output creation. Source revision is an operator-supplied identifier, not a
new source attestation.

For `learned_order`, supply both `--policy` and `--training-report` from the layout
learner. Section-only candidate policies are not layout policies. Price-only execution
rejects both learned inputs. `--prefix-target-count` is required only with `staged`;
a passing prefix cannot authorize final selection. The full accepted candidate must
receive complete fresh analysis and verification. Existing output directories are
not overwritten.

The original result graph is written by the existing strategy executor.
`strategy-runtime.json` adds a separate report-hash-bound observation from argument
parsing through report persistence, including input reads and strategy execution.
It excludes interpreter startup/imports, the runtime sidecar/stdout write and HTTP/UI
review. It reports no new fit or proved net savings. Historical fit costs remain in
the strategy result and are not newly executed or double-counted by this sidecar.

## Focused validation

The new CLI test module passed 16 tests in 50.57 seconds: six actual reference
executions cover both strategies and all three execution modes, preserving selected
full verification, original result identities and enclosing runtime scope. Ten
negative cases cover duplicate JSON, extra fields, path traversal, absolute and
escaping-symlink paths, duplicate candidates, boolean price, improper prefix length,
forbidden learned inputs for price order and missing learned inputs. All reject
before creating the output directory. The fixtures use a small synthetic-price
layout cohort; they do not establish new generalization or acceleration.

Ruff and mypy passed for the CLI; Ruff passed for its tests. An initial fixture-import
lint diagnostic was resolved. This is local testing with the new CLI changes present,
not a hosted receipt for this later code.

## Hosted integration evidence at the preceding source

[Native Frame Alpha Clean Install run 34723974649](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34723974649)
completed successfully at `dea625b1a023954a3c2f7a39168f9f55cddcdc6a`.
Windows and Linux builds and clean-install jobs, cross-platform comparison and the
packaged browser replay all succeeded. This confirms that the earlier package-root
manifest repair cleared the observed installation path failure at that source.

`produce-unprivileged` and `attest-fresh-hosted-no-repository-code` were skipped:
the workflow requires a non-PR event on main for those jobs, whereas this run was a
pull-request run. No event condition was changed, and no signed release, owner/legal
approval, independent structural-physics qualification or all-repository completion
is inferred. The accompanying summary records the exact run, job IDs and step
conclusions, separately from the later CLI's local tests.
