#!/usr/bin/env python3
"""Verify bounded Rust-native Workbench C5 ownership and executable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/Cargo.toml": ('"crates/structural-workbench"',),
    "native/crates/structural-workbench/src/lib.rs": (
        "structural-native-workbench-session.v1",
        "WorkbenchStageV1",
        "execute_model_ir_native_analysis",
        "execute_native_mgt_import",
        "initialize_model_ir_linear_from_mgt_paths",
        "execute_external_comparison",
        "execute_pdf_report",
        "execute_localized_pdf_report",
        "write_atomic_file",
        "fs::rename",
        "workbench_stage_gap",
        "workbench_artifact_inventory_mismatch",
        "workbench_mgt_import_binding_mismatch",
        "structural-native-workbench-view.v1",
        "structural-native-workbench-review.v1",
        "structural-native-workbench-export.v1",
        "publish_review",
        "inspect_json",
        "linear_report_text",
        "ndtha_response_view_text",
        "ndtha_response_view_text_localized",
        "fixed_guided_deformed_shape_view_text",
        "fixed_guided_deformed_shape_view_text_localized",
        "export_localized_pdf",
        "render_model_topology_view",
        "render_model_topology_view_file_localized",
        "render_model_topology_view_localized",
        "export_json",
        "workbench_review_binding_mismatch",
    ),
    "native/crates/structural-workbench/src/report_view.rs": (
        "structural-native-workbench-linear-report.v1",
        "WorkbenchReportLocaleV1",
        '"en-US"',
        '"ko-KR"',
        "safe_terminal_text",
        "not WCAG, PDF/UA",
    ),
    "native/crates/structural-workbench/src/result_view.rs": (
        "structural-native-workbench-ndtha-response-view.v1",
        "WorkbenchResultChannelV1",
        '"top-displacement"',
        '"drift-ratio"',
        '"base-shear"',
        '"residual-inf"',
        "WORKBENCH_RESULT_VIEW_MAX_COUNT_V1",
        "ResultIR v1 does not carry dt_s",
        "not a time reconstruction, 3D/deformed/modal/contour view",
        "시간값을 추론하지 않습니다",
    ),
    "native/crates/structural-workbench/src/deformed_view.rs": (
        "structural-native-workbench-fixed-guided-deformed-view.v1",
        "fixed_guided_frame3d_x",
        "validate_model_bytes",
        "Top displacement global X (m)",
        "C++ fixed-guided adapter execution",
        "C++ 고정-가이드 어댑터 실행",
        'semantic_snapshot_value: "verified"',
        "not_general_nodal_displacement_3d_modal_contour",
    ),
    "native/crates/structural-workbench/src/model_view.rs": (
        "structural-native-model-topology-view.v1",
        "ModelTopologyProjectionV1",
        "validate_model_bytes",
        'semantic_snapshot: "C++ semantic snapshot"',
        "Structural Native Workbench - 모델 위상 뷰",
        "C++ 의미 스냅샷",
        "workbench_model_view_semantics_invalid",
        "bounded_general_modelir_semantic_snapshot_terminal_topology_projection",
    ),
    "native/crates/structural-workbench/src/model_edit.rs": (
        "structural-native-model-edit-receipt.v1",
        "structural-native:model-edit-node.v1",
        "structural-native:model-edit-nodal-load.v1",
        "structural-native:model-edit-constraint-value.v1",
        "structural-native:upstream-provenance",
        "structural-native-model-editor",
        "edit_model_nodal_load_components",
        "edit_model_constraint_value",
        "validate_model_bytes",
        "workbench_model_edit_no_change",
        "workbench_model_edit_semantics_invalid",
        "bounded_cpp_revalidated_modelir_node_coordinate_edit",
        "bounded_cpp_revalidated_existing_modelir_nodal_load_component_edit",
        "bounded_cpp_revalidated_existing_modelir_restrained_dof_prescribed_value_edit",
    ),
    "native/crates/structural-workbench/src/main.rs": (
        'Some("model-view")',
        'Some("model-edit-node")',
        'Some("model-edit-nodal-load")',
        'Some("model-edit-constraint-value")',
        'Some("import")',
        'Some("import-mgt")',
        'Some("import-mgt-model-linear")',
        'Some("validate")',
        'Some("run")',
        'Some("resume")',
        'Some("compare")',
        'Some("report")',
        'Some("report-view")',
        'Some("result-view")',
        'Some("result-deformed-view")',
        'Some("report-export-pdf")',
        'Some("interactive")',
        'Some("workflow")',
        'Some("workflow-mgt")',
        'Some("workflow-mgt-model-linear")',
        'Some("inspect")',
        'Some("review")',
        'Some("review-show")',
        'Some("export")',
    ),
    "native/crates/structural-workbench/tests/native_workbench_e2e.rs": (
        "clean_process_restart_workflow_recovers_and_is_bitwise_deterministic",
        "command.env_clear()",
        "restore pre-run durable session",
        "assert_eq!(files.len(), 29)",
        "invalid_transition_and_import_tamper_fail_closed",
        "mgt_import_restart_workflow_preserves_health_and_is_bitwise_deterministic",
        "blocked_mgt_health_cannot_create_an_analysis_workspace",
        "assert_eq!(files.len(), 34)",
        "native_review_inspect_and_export_are_deterministic_and_tamper_evident",
        "localized_linear_report_view_is_utf8_deterministic_and_hash_bound",
        "ndtha_response_view_is_windowed_deterministic_hash_bound_and_terminal_gated",
        "fixed_guided_deformed_view_is_profile_bound_deterministic_and_terminal_gated",
        "localized_pdf_export_is_deterministic_hash_bound_and_non_mutating",
        "general_modelir_topology_view_is_cpp_verified_deterministic_and_fail_closed",
        "node_coordinate_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "node_coordinate_edit_preserves_analysis_blockers_without_promotion",
        "nodal_load_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "nodal_load_edit_preserves_analysis_blockers_without_promotion",
        "constraint_value_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "constraint_value_edit_preserves_source_analysis_blockers_without_promotion",
        "workbench_review_exists",
        'view["human_review"]["automatically_inferred"]',
        "sha256:f59193c725e236e4d824b9f2422befce5205050677489e6fc13bb8a31d580ceb",
        "sha256:35f2bebb41411b31cba9e0c395ba74f914097498e8da63e4b14d72704f06c197",
    ),
    "native/crates/structural-workbench/tests/model_ir_linear_workbench_e2e.rs": (
        "clean_environment_mgt_linear_workflow_preserves_import_health_and_restart_identity",
        "simulate MGT linear process death",
        "workbench_mgt_import_binding_mismatch",
    ),
    "docs/native/rust-native-workbench-v1.md": (
        "Import` strictly parses",
        "Rust -> C ABI -> C++",
        "process died while replacing the session file",
        "original MGT bytes",
        "does not yet replace all React/TypeScript UI behavior",
        "explicit human review and handoff export",
        "UTF-8 linear report view",
        "bounded NDTHA response-history view",
        "fixed-guided deformed-shape view",
        "embedded-font PDF export",
        "general ModelIR terminal topology view",
        "provenance-bound ModelIR node-coordinate edit",
        "nodal-load edit",
        "constraint-value editor",
        "does not infer the human decision",
        "HIP C2",
        "C6",
    ),
    "docs/native/localized-terminal-result-views-v1.md": (
        "en-US",
        "ko-KR",
        "Omitting `--locale` preserves the original `en-US` bytes",
        "append-only distribution v12 receipt",
        "not WCAG conformance",
    ),
    "docs/native/localized-modelir-topology-view-v1.md": (
        "en-US",
        "ko-KR",
        "Omitting `--locale` preserves the original `en-US` bytes exactly",
        "append-only distribution v13 receipt",
        "not general localization",
    ),
    "docs/native/modelir-nodal-load-edit-v1.md": (
        "model-edit-nodal-load",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-nodal-load.v1",
        "load_pattern",
        "all-zero invalid load pattern",
        "C6 remain open",
    ),
    "docs/native/modelir-constraint-value-edit-v1.md": (
        "model-edit-constraint-value",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-constraint-value.v1",
        "implicit previous value of zero",
        "C6 remain open",
    ),
}


def check_native_workbench(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["native_workbench"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"native_workbench_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("native_workbench_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("native_workbench_capability_gate_not_c5")
    if row.get("owner") != "structural-workbench":
        blockers.append("native_workbench_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "Import -> Validate -> Run -> Resume -> Compare -> Report",
        "Inspect -> Report-view -> Result-view -> Result-deformed-view -> Review -> Export",
        "direct Rust product-library calls",
        "MGT",
        "process death after checkpoint publication",
        "no Python, Node, browser, CLI subprocess",
        "never inferred",
        "English/Korean UTF-8 linear report view",
        "English/Korean embedded-font PDF export",
        "general ModelIR terminal topology view",
        "closed `en-US`/`ko-KR` paths",
        "provenance-bound ModelIR node-coordinate edit",
        "nodal-load edit",
        "constraint-value editor",
        "English/Korean bounded self-hashed NDTHA response-history view",
        "English/Korean exact-profile deformed-shape view",
        "React/TypeScript removal",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"native_workbench_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"native_workbench_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"native_workbench_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-rust-workbench-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
        "claim_boundary": (
            "This validates one bounded terminal-native C5 workflow. It does not prove general "
            "GUI replacement, live external solver execution, protected HIP C2, packaging, or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_workbench(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native Rust Workbench contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
