# Full Python baseline and native RC wire migration

The complete local Python suite at `df60b7d3913f8fe095788f07ace95302d02f6cd3`
finished with **11,084 passed, 130 failed and 52 skipped** in 6,591.38 seconds.
The source HEAD and clean working tree were unchanged through completion.
This is a failed baseline, not current-head qualification. The accompanying
[machine-readable record](full-suite-native-wire-20260913.summary.json) includes
raw log/XML digests and failure counts for every affected module.

The command was `python3 -m pytest -q --junitxml=<root>/full.xml
--basetemp=<root>/pytest-temp`, with `PYTHONPATH=src`,
`OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`. There was no subset,
max-failure cutoff or manual deselection. Hosted evidence preparation was not
performed before this local baseline. Missing case-package manifests, stale
source receipts and dependent matrix/attestation failures are visible in the
results; their counts must not be interpreted as independent solver defects.
Conversely, inventory rebuild, medium-scale and other assertion failures remain
open pending individual diagnosis. The remaining failures are not all assigned
to a single cause.

## Two bounded corrections

The Python ModelIR schema already admitted intermediate steel layers, but its
packaged native copy omitted that property. Native PR Fast run `34727319739`
failed its byte-identical schema test in both Rust quality and ModelIR jobs.
The native schema now includes the same property, and the exact-integer guard
includes nested `bar_count`. New wire regressions preserve the field, bind its
count to document identity, and reject ten malformed or out-of-range inputs.
All **31 structural-contracts tests passed**, including 11 wire tests, after
application to this checkout. Clippy with warnings denied also passed in the
isolated tracked-source validation snapshot. These are wire/schema checks,
not proof of semantic validity or physical accuracy.

One Python baseline failure expected request v4 to be unsupported although v4
is the existing terminal-polishing request format. The rejection test now uses
unknown v999, retains v1/v2 downgrade rejection, and adds explicit v4 configuration
preservation. The production decoder is unchanged. All **67 tests in the learning
process module passed**. Ruff checks/format, cargo format and diff whitespace
checks passed. The 31 and 67 counts are separate suites, not an updated full-suite
total. The full baseline has not been rerun after these changes.

## Hosted and research boundaries

At the baseline HEAD, Repository Python Tests run `34727319700` passed its
development-contract job (951 tests), but all four full-suite shards failed
evidence materialization and skipped their test execution. The observed blockers
include `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. These gates and comparison
tolerances remain unchanged. New-head hosted results must be checked separately.

This work repairs schema consistency and an obsolete test expectation. It does
not establish learned net benefit, admit external training data, close independent
physical validation, or make PR #439 ready to merge.
