# Positive enclosing intervals for strategy cost comparison

The standalone CLI cohort comparator previously accepted an execution whose CLI,
search and arm wall intervals were all zero. A controlled rehashed metadata
counterexample reproduced this for each strategy in a two-pair cohort. Other
positive repetitions could then produce a training-inclusive aggregate ratio;
a zero learned interval could also appear as a zero per-pair ratio. These were
synthetic clock values, not measured solver performance.

Each admitted CLI execution now requires a positive wall interval, in addition to
the existing safe-integer, nested-interval, source, selection and work contracts.
A malformed execution rejects the comparison instead of disappearing from its
denominator. CPU and nested counters keep their existing nonnegative semantics.
Workbench applies the same positive CLI interval rule. This change does not
rewrite historical evidence or turn metadata validation into clock attestation.

The Python regression first failed for both strategies, then passed after the
change. Cost and portable cohort tests: **42 passed in 1.79 s**. Workbench cohort
contracts: **20 passed in 4.8 s**. Ruff, scoped mypy and TypeScript checks passed.
The frontend zero-clock case uses the original positive inner intervals; it
checks rejection, while the Python regression isolates the all-zero enclosing
interval issue. No structural solve or training fit was added.

The existing frontend mutation tests also supplied the previous report hash as
part of their replacement fields. That produced an invalid self-hash and could
reject before testing the intended content. They now exclude the old hash and
explicitly verify the new self-hash before testing modified training costs,
ratios, counts, paths, execution bindings, extra claims and runtime metadata.
Those rejection tests still pass after reaching the actual content boundary.

This closes a cost-accounting input gap, not learned net benefit, independent
physical validation, whole-user-flow timing, full hosted CI or the broader roadmap.

## Shared mutation helper follow-up

Three additional controls supplied full replacement objects for a cohort manifest,
a standalone plan and a standalone result. All three initially failed the actual
Workbench self-hash validator. The shared `rebind` helper now excludes the target
hash field from both preserved input fields and replacement fields before hashing.
The old hash can no longer become part of the new digest when callers supply a
whole object. Other replacement fields remain intact.

Standalone search mutation tests now explicitly verify the replacement plan and
result self-hashes before asking the search validator to reject changed strategy,
schema, arm membership, oracle, training, quantities, cost, selection and work.
The combined cohort/search contracts pass **71 tests in 6.6 s**, including the
three previously failing full-object controls. TypeScript and diff checks pass.
This strengthens negative-test evidence; it adds no new physical or speed result.
