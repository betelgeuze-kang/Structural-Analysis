# Goal
Find the smallest local change that makes product name/version consistency part of the canonical readiness snapshot without promoting readiness.

# Scope
- Inspect only:
  - `scripts/build_product_readiness_snapshot.py`
  - `tests/test_build_product_readiness_snapshot.py`
  - `package.json`
  - `pyproject.toml`
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
- Do not edit files.
- Do not run broad test suites.
- Do not push, merge, fetch, or use network.

# Questions
1. Where should a mismatch between `package.json` and `pyproject.toml` be represented in `product_readiness_snapshot.json`?
2. What blocker names and component fields would fit the existing snapshot style?
3. Which focused tests should be added or adjusted?

# Output
Return only:
- recommended files to edit
- exact proposed blocker/component field names
- focused tests to run
- any risks or blockers
