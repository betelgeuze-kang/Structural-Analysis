# foundation_realish

Small file-based fixture set for foundation-bearing regression coverage.

This fixture is intentionally minimal and is currently used for:

- `parse_midas_mgt_to_json_npz.py`
- `generate_design_optimization_dataset.py`
- `generate_foundation_optimization_artifact.py`
- `generate_foundation_optimization_report.py`

The set now includes two raw source cases:

- `foundation_small.*`: `raft + pile-cap + beam`
- `foundation_deep_small.*`: `mat + caisson + pile + beam`

That keeps the regression surface honest across more than one foundation
vocabulary family while still staying lightweight enough for parser-level tests.

Fixtures:

- `foundation_small.mgt`: explicit `RAFT` / `PILE-CAP` section labels
- `foundation_generic_sections.mgt`: generic `DBUSER` section names with foundation scope carried only by group labels
- `foundation_parser_drop_small.mgt`: raw source carries `FOUNDATION` only in group plane type so parsed model drops the token and should trigger `parser_drop_suspected`
