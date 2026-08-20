#!/usr/bin/env python3
"""Verify bounded typed-ModelIR linear Workbench C5 evidence without promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/model_linear_recovery.rs": (
        "structural-model-ir-linear-result-recovery-ir.v1",
        "parse_model_ir_linear_result_recovery_ir_v1",
        "model_ir_linear_recovery_noncanonical",
        "model_ir_linear_recovery_jvp_mismatch",
        "model_ir_linear_recovery_equilibrium_mismatch",
        "model_ir_linear_recovery_inactive_displacement_nonzero",
        "model_ir_linear_recovery_summary_invalid",
        "model_ir_linear_recovery_solution_mismatch",
        "fallback_count != 0",
    ),
    "native/crates/structural-contracts/src/model_linear_comparison.rs": (
        "structural-model-ir-linear-external-result.v1",
        "structural-model-ir-linear-external-comparison-ir.v1",
        "global_dof_index % 6",
        "ExternalComparisonStatusV1",
    ),
    "native/crates/structural-cli/src/model_linear_comparison.rs": (
        "execute_model_ir_linear_external_comparison",
        "publish_model_ir_linear_external_comparison",
        "source_recovery_hash",
        "structural-native-model-ir-linear-comparison-receipt.v1",
    ),
    "native/crates/structural-cli/src/model_linear_product.rs": (
        "parse_model_ir_linear_result_recovery_ir_v1",
        "result-recovery-ir.json",
    ),
    "native/crates/structural-report/src/pdf.rs": (
        "render_sparse_linear_pdf_v1",
        "build_sparse_linear_pdf_bytes",
        "sparse-report-pdf.v1",
        "validate_deterministic_pdf_v1",
    ),
    "native/crates/structural-report/src/localized_pdf.rs": (
        "render_sparse_linear_localized_pdf_v2",
        "render_model_ir_linear_engineering_localized_pdf_v3",
        "verify_exact_sparse_projection",
    ),
    "native/crates/structural-cli/src/report.rs": (
        "execute_sparse_linear_pdf_report",
        "structural-native-sparse-linear-pdf-report-receipt.v1",
        "sparse_linear_pdf_report",
        "execute_sparse_linear_localized_pdf_report",
        "structural-native-sparse-linear-localized-pdf-report-receipt.v2",
        "execute_model_ir_linear_engineering_localized_pdf_report",
        "structural-native-model-ir-linear-engineering-localized-pdf-report-receipt.v3",
    ),
    "native/crates/structural-workbench/src/lib.rs": (
        "WorkbenchAnalysisProfileV1",
        "ModelIrLinearCpuV1",
        "initialize_model_ir_linear_from_paths",
        "initialize_model_ir_linear_from_mgt_paths",
        "initialize_model_ir_linear_from_mgt",
        "execute_model_ir_linear_analysis",
        "checkpoint.mlpcp",
        "execute_model_ir_linear_external_comparison",
        "publish_model_ir_linear_pdf_report",
        "execute_sparse_linear_pdf_report",
        "execute_sparse_linear_localized_pdf_report",
        "execute_model_ir_linear_engineering_localized_pdf_report",
        "export_model_ir_linear_localized_pdf",
        "structural-native-model-ir-linear-pdf-report-receipt.v1",
        "sparse_linear_pdf_report",
        "pdf_ready_document_source",
        "workbench_profile_unsupported",
    ),
    "native/crates/structural-workbench/src/main.rs": (
        'Some("import-model-linear")',
        'Some("import-mgt-model-linear")',
        'Some("workflow-model-linear")',
        'Some("workflow-mgt-model-linear")',
        "run_model_ir_linear_workflow",
    ),
    "native/crates/structural-contracts/tests/model_ir_linear_comparison_wire.rs": (
        "recovered_result_and_external_dof_comparison_are_strict_and_self_hashed",
        "duplicate_mapping_and_recovery_tamper_fail_closed",
    ),
    "native/crates/structural-workbench/tests/model_ir_linear_workbench_e2e.rs": (
        "clean_environment_linear_workflow_restarts_and_reprojects_exactly",
        "clean_environment_mgt_linear_workflow_preserves_import_health_and_restart_identity",
        "linear_profile_rejects_wrong_external_mapping_before_workspace_publication",
        "command.env_clear()",
        'command.env("PATH", "/nonexistent")',
        "simulate crash before session persistence",
        "simulate MGT linear process death",
        "restart drift",
        "validate_deterministic_pdf_v1",
        "validate_deterministic_localized_pdf_v2",
        "localized linear export drift",
        "tampered_pdf",
        "sparse_linear_pdf_report",
        "pdf_ready_document_source",
        "workbench_profile_unsupported",
    ),
    "docs/native/modelir-linear-workbench-v1.md": (
        "Import -> Validate -> Run -> Resume -> Compare -> Report",
        "PDF-ready Markdown",
        "deterministic single-page sparse PDF",
        "embedded-font localized engineering-summary PDF v3",
        "import-mgt-model-linear",
        "render_sparse_linear_pdf_v1",
        "process death after atomic checkpoint publication",
        "no Python, Node, browser, CLI subprocess",
        "protected-runner HIP C2",
        "authoritative numerical C2/C3",
        "C6 decommission",
    ),
}


def check_model_ir_linear_workbench(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["modelir_linear_workbench"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"model_ir_linear_workbench_manifest_invalid:{exc}")
        row = {}
        payload = {}

    if row.get("status") != "implemented":
        blockers.append("model_ir_linear_workbench_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("model_ir_linear_workbench_gate_not_c5")
    if row.get("owner") != "structural-workbench":
        blockers.append("model_ir_linear_workbench_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "model_ir_linear_cpu_v1",
        "Import -> Validate -> Run -> Resume -> Compare -> Report",
        "real PCG checkpoint.mlpcp",
        "typed recovered global-DOF",
        "PDF-ready Markdown",
        "deterministic single-page sparse PDF",
        "clean-environment process restart",
        "no Python, Node, browser, CLI subprocess",
        "existing fixed-guided NDTHA session and receipt bytes",
        "embedded-font localized engineering-summary PDF v3",
        "original MGT bytes",
        "import-health",
        "approved protected-runner HIP C2",
        "authoritative numerical C2/C3",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"model_ir_linear_workbench_scope_token_missing:{token}")

    numerical_gates: dict[str, object] = {}
    try:
        capabilities = payload["capabilities"]
    except (KeyError, TypeError):
        capabilities = {}
    for name in ("dense_assembly_cpu", "sparse_linear_solver_cpu"):
        candidate = capabilities.get(name, {}) if isinstance(capabilities, dict) else {}
        if not isinstance(candidate, dict) or candidate.get("cutover_gate") != "C1":
            blockers.append(f"{name}_sequential_gate_not_c1")
            continue
        numerical_gates[name] = candidate.get("cutover_gate")
        gate_claim = str(candidate.get("claim", ""))
        for token in ("sequential gate remains C1", "protected-runner"):
            if token not in gate_claim:
                blockers.append(f"{name}_nonpromotion_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"model_ir_linear_workbench_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"model_ir_linear_workbench_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-model-ir-linear-workbench-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "sequential_numerical_gates": numerical_gates,
        "blockers": blockers,
        "claim_boundary": (
            "This check closes only bounded typed-ModelIR CPU linear Workbench C5 composition. "
            "It includes deterministic standard-font and fixed-locale embedded-font sparse PDFs "
            "but cannot promote numerical C2, authoritative C3, HIP C2, general PDF authority, "
            "or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_model_ir_linear_workbench(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native ModelIR linear Workbench contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
