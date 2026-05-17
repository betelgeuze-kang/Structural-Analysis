# Structure Viewer Product Workspace

The source viewer now has a project-workspace layer on top of the existing static 3D viewer. The goal is desktop-first engineer-in-loop review: browse registered projects, switch drawing variants, select members, inspect evidence-aware explanations, and export review reports without splitting the viewer into more standalone HTML files.

## Current Interface

- Project manifest schema: `structure-viewer-project-manifest.v1`
- Standard viewer query:

```text
src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized
```

- Backward-compatible aliases still work:

```text
src/structure-viewer/index.html?preset=midas33_optimized
src/structure-viewer/index.html?preset=real_drawing_private_3d
```

## Product Features

- Project browser: registered MIDAS33, real drawing, and release visualization entries are normalized into project/drawing rows with status badges. The bundled release project currently covers the OPSTOOL 606m outrigger plus seven megatall optimized/compare triples (`baseline`, `after_only`, `ai_compare`) so the viewer can browse the release optimization set from one manifest.
- Drawing search: the project browser supports `drawing_query` filtering across drawing title, id, source family, references, and quality flags without leaving the current viewer.
- Variant navigation: `baseline`, `optimized`, and `compare` buttons keep URL state explicit and reload through the existing preset/artifact loader.
- Drawing evidence drilldown: the selected drawing now shows review status, count verification/source, baseline/optimized refs, artifact path, quality flags, and registered variants directly in the project browser.
- Drawing review card: quality flags are normalized into `critical`, `warning`, and `info` issues. The selected drawing shows `상용 검토 가능`, `제한적 검토`, or `검토 불가`, issue counts, recommended action, and severity rows. Drawing list badges use the same issue-count model, so a blocked or limited drawing is visible before opening it.
- Before/optimized work surface: registered drawings can expose member-count, weight/cost proxy, risk-movement, and member-level comparison rows. The viewer now provides fixed comparison filters for `changed`, `reduced`, `retained`, `risk_up`, and `missing_evidence`; manifest-level deltas are shown as derived proxy evidence when exact member rows are not available. When exact member rows exist, the active comparison filter is also promoted into 3D highlight state and shown as an exact-member highlight count in the comparison panel/report.
- Artifact count verification: `npm run verify:viewer-manifest` reads each `artifact_count_source` JSON and verifies the manifest member counts against `interactive_3d.baseline_segment_count` and `interactive_3d.after_segment_count`. The project browser, viewer report panel, and exported HTML report surface the same count-verification status/source, so demo/review output does not rely on a separate terminal log.
- Drawing quality: each drawing carries `commercial_review_status=ready|needs_review|blocked` plus quality flags such as `load_model_missing`, `empty_geometry`, `missing_members`, `scale_outlier`, `axis_flipped_review`, and `provenance_missing`.
- Input normalization: `viewer-project-workspace.js` exposes `normalizeProjectManifestRow()` and `buildProjectManifestFromRows()` so MIDAS, IFC, JSON, and CSV rows can be converted into the same workspace manifest contract before the viewer accepts them as reviewable drawings.
- Explainability panel: selected members show grouped section/material/load, D/C usage, review status, optimization delta, weight/cost proxy, optimization rationale, risk focus, and whether each value is `exact source`, `derived proxy`, or `missing evidence`. The checklist is fixed to `하중 확인 필요`, `DCR 재검토`, `단면 변경 확인`, and `근거 누락 확인`.
- Report export: the viewer exports an HTML engineer-in-loop review report and a local audit JSONL file for the active project/drawing. The report includes the drawing review card, issue list, before/after member comparison, selected member checklist, local review note, and a viewer screenshot marker. PDF export is available through Playwright:

```bash
npm run export:viewer-report-pdf -- --query "project=midas33_release&drawing=midas33_optimized&variant=optimized" --out /tmp/structure_viewer_report.pdf
npm run verify:viewer-report-pdf
```

- Local ops state: recent project selections, active member/filter, review notes, export history, and audit events are stored in browser local storage as a reference control-plane surface. Audit JSONL and project-bundle JSON export give demos/reviews a portable activity trail without turning the static viewer into a SaaS tenant store.

## Verification

Run the focused checks:

```bash
python3 -m pytest -q tests/test_structure_viewer_project_workspace_contract.py \
  tests/test_structure_viewer_member_comparison_model_contract.py \
  tests/test_structure_viewer_explainability_report_contract.py \
  tests/test_structure_viewer_local_ops_state_contract.py
npm run verify:viewer-manifest
npm run verify:frontend-browser-smoke -- --mode minimal
```

Full viewer verification:

```bash
python3 -m pytest -q tests/test_structure_viewer_*
npm run verify:viewer-manifest
npm run verify:frontend-browser-smoke
npm run verify:viewer-report-pdf
python3 scripts/verify_quality_gate.py --mode pr
```

Commercial claim remains bounded to `engineer-in-loop commercial assist only` until strict EB/RH external evidence is attached.
