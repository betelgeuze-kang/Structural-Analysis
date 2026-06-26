# Cursor Worker Slice: Phase 4 GUI Story/Member/Mode Traceability Audit

Goal:
Audit the GUI/comparison model surface for the Phase 4 requirement that comparison results are traceable by member, story, and mode without claiming Phase 4 closure.

Scope:
- Inspect only:
  - `src/structure-viewer/viewer-commercial-tool-crosswalk-model.js`
  - `src/structure-viewer/viewer-report-export.js`
  - `tests/test_structure_viewer_commercial_tool_crosswalk_model_contract.py`
  - `scripts/build_phase4_commercial_operator_reference_contract.py`
  - `scripts/build_phase4_commercial_operator_reference_ingest_validator.py`
- Do not edit protected evidence receipts or ledgers.
- Do not claim two-reference-solver comparison or Phase 4 closure.

Report:
- Whether the viewer model exposes trace fields for member, story, and mode.
- Exact test assertions that would prove trace coverage.
- Any claim-boundary risk if traceability exists only as a GUI/schema contract while operator outputs remain absent.

Verification criteria:
- Member/story/mode trace keys must be explicit and stable.
- Missing story or mode must be visible as missing, not silently treated as pass.
- Commercial outputs remain comparison references, not absolute truth.
- Operator output absence and two-reference-solver blockers remain visible.
