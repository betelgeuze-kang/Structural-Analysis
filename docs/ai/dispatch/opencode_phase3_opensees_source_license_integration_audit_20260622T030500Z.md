# OpenCode Worker Slice: Phase 3 OpenSees Source/License Integration Audit

## Goal
Audit the Phase 3 OpenSees medium source/license receipt integration for claim-boundary accuracy and reproduction coverage.

## Scope
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_opensees_source_license_receipt.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py`
- `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- matching tests under `tests/test_build_phase3_*` and `tests/test_run_phase3_*`

## Candidate checks
- OpenSees medium candidate must stay `blocked`; do not promote Phase 3, Developer Preview RC, license, redistribution, source URL, or reference-output closure.
- Acquisition row wording should not imply an authoritative official source URL if only local candidate Tcl/checksum/topology evidence is attached.
- Clean checkout and git-clean-clone reproduction should include the source/license receipt script, generated receipt, local OpenSees inputs, and focused tests where appropriate.
- Reproducibility bundle/checksum logic should include the receipt without creating a circular unstable checksum.

## Verification criteria
- Report changed files, or say no edits.
- Report focused commands run and their status.
- Report any blockers or claim-boundary risks.
- Keep output concise.
