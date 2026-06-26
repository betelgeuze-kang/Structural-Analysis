# OpenCode worker slice: Phase 3 OpenSees source/license receipt

Goal:
- Add a blocked but authoritative source/license receipt for the `opensees_scbf16b_medium_candidate` Phase 3 lane.
- Do not mark license, redistribution, source URL, reference outputs, or Phase 3 closure as passed unless evidence exists.

Scope:
- Inspect:
  - `src/structural_analysis/benchmark/acquisition.py`
  - `scripts/build_phase3_benchmark_acquisition_artifacts.py`
  - local OpenSees artifacts under `implementation/phase1/open_data/megastructure/opensees/`
  - `implementation/phase1/opensees_topology_report.json`
  - `implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json`

Expected behavior:
- New receipt should record local candidate checksums and existing topology/parser receipt.
- It must keep `source_url_verified=false`, `license_review_status=blocked`, `redistribution_allowed=false`, and `commercial_use_allowed=false` unless a real authoritative source/license is attached.
- Acquisition plan should reference the receipt without turning Phase 3 or the source row ready.

Verification:
- Focused pytest for acquisition artifacts.
- Artifact regeneration/check mode stays consistent.
- Ruff on touched files.

Output:
- Changed files.
- Test results.
- Claim-boundary concerns.
