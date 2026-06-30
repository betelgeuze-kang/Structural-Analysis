"""Acquisition policy helpers for non-seed Phase 3 benchmark lanes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT = 10


@dataclass(frozen=True)
class BenchmarkAcquisitionSource:
    source_id: str
    lanes: tuple[str, ...]
    source_kind: str
    truth_class: str
    acquisition_mode: str
    source_url_or_doi: str
    license_status: str
    redistribution_allowed: bool
    commercial_use_allowed: bool
    checksum_status: str
    expected_output_status: str
    normalization_status: str
    reference_result_status: str
    blockers: tuple[str, ...]
    claim_boundary: str
    local_candidate_artifacts: tuple[dict[str, Any], ...] = ()
    existing_receipts: tuple[dict[str, Any], ...] = ()
    source_license_receipt_path: str = ""

    def row(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lanes"] = list(self.lanes)
        payload["blockers"] = list(self.blockers)
        payload["selected_benchmark_lanes"] = list(self.lanes)
        payload["ready_for_phase3_quantity_credit"] = False
        payload["local_candidate_artifacts"] = list(self.local_candidate_artifacts)
        payload["existing_receipts"] = list(self.existing_receipts)
        payload["source_license_receipt_path"] = self.source_license_receipt_path
        return payload


def phase3_non_seed_acquisition_sources() -> list[BenchmarkAcquisitionSource]:
    return [
        BenchmarkAcquisitionSource(
            source_id="opensees_scbf16b_medium_candidate",
            lanes=("opensees-medium",),
            source_kind="local_opensees_candidate_source_url_unverified",
            truth_class="independent_reference",
            acquisition_mode="local_candidate_present_authoritative_source_and_license_pending",
            source_url_or_doi="local_candidate_source_url_unverified:SCBF16B",
            license_status="blocked_no_authoritative_license_source_attached",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="local_candidate_checksum_attached_source_url_unverified",
            expected_output_status="missing_until_reference_outputs_ingested",
            normalization_status="not_started",
            reference_result_status="not_ingested",
            blockers=(
                "source_url_verification_pending",
                "license_review_pending",
                "reference_outputs_missing",
                "normalization_not_implemented",
                "opensees_medium_runner_command_missing",
                "opensees_medium_scorecard_execution_missing",
                "medium_model_pass_or_review_missing",
            ),
            claim_boundary=(
                "OpenSees medium lane has local SCBF16B candidate artifacts and topology "
                "parser evidence, but authoritative source URL, upstream license text, "
                "redistribution rights, commercial use rights, reference output ingest, "
                "normalization, and OpenSees medium scorecard execution are still not closed."
            ),
            local_candidate_artifacts=(
                {
                    "case_id": "SCBF16B_shell_beam_mix",
                    "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
                    "format": "tcl",
                    "origin": "global_authority",
                    "sha256": "ceb64448b2a04afd19f57a6652aac4859760c511fd3bb447c41991f7c415bcdc",
                    "size_bytes": 118474,
                    "parser_contract_ready": True,
                    "source_of_checksum": (
                        "implementation/phase1/release/benchmark_expansion/"
                        "opensees_canonical_breadth_report.json"
                    ),
                },
                {
                    "case_id": "SCBF16B",
                    "path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                    "format": "tcl",
                    "origin": "global_authority",
                    "sha256": "309234fd42a58369a6d41198290527c6a86fee7da38c38a2fcbf625318720b80",
                    "size_bytes": 118066,
                    "parser_contract_ready": True,
                    "source_of_checksum": (
                        "implementation/phase1/release/benchmark_expansion/"
                        "opensees_canonical_breadth_report.json"
                    ),
                },
            ),
            existing_receipts=(
                {
                    "path": "implementation/phase1/opensees_topology_report.json",
                    "status": "pass",
                    "contract_pass": True,
                    "source_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
                    "source_sha256": "ceb64448b2a04afd19f57a6652aac4859760c511fd3bb447c41991f7c415bcdc",
                    "node_count": 426,
                    "beam_element_count": 166,
                    "shell_element_count": 5,
                    "claim_boundary": (
                        "Topology parser evidence only; this is not reference result ingest, "
                        "solver accuracy, or Phase 3 quantity credit."
                    ),
                },
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase3_medium_model_scorecard_readiness_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "required_medium_model_count": 5,
                    "current_medium_model_scorecard_count": 0,
                    "pass_or_approved_review_count": 0,
                    "local_candidate_artifact_count": 2,
                    "claim_boundary": (
                        "OpenSees medium scorecard readiness contract only; local "
                        "checksum/topology evidence remains parser-only and is not "
                        "reference-output ingest, normalization, scorecard execution, "
                        "or PASS/REVIEW benchmark evidence."
                    ),
                },
            ),
            source_license_receipt_path=(
                "implementation/phase1/release_evidence/productization/"
                "phase3_opensees_medium_source_license_receipt.json"
            ),
        ),
        BenchmarkAcquisitionSource(
            source_id="opensees_megatall_model_2_large",
            lanes=("opensees-megatall", "large-model-performance"),
            source_kind="official_open_solver_large_model",
            truth_class="independent_reference",
            acquisition_mode="nightly_or_workstation_download_after_license_review",
            source_url_or_doi="official_url_pending_license_review:opensees-megatall-model-2",
            license_status="review_required_before_bundling_or_ci_download",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="missing_until_source_acquired",
            expected_output_status="missing_until_reference_outputs_ingested",
            normalization_status="not_started",
            reference_result_status="not_ingested",
            blockers=(
                "source_url_verification_pending",
                "license_review_pending",
                "checksum_missing",
                "reference_outputs_missing",
                "nightly_lane_not_configured",
                "large_model_execution_receipt_missing",
                "large_model_scorecard_or_review_missing",
            ),
            claim_boundary=(
                "OpenSees mega-tall/large-model policy only. A local operator receipt "
                "runner exists, but this row is not a large-model execution, memory, "
                "runtime, or accuracy receipt."
            ),
            existing_receipts=(
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase3_large_model_runner_readiness_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "required_large_model_count": 2,
                    "current_large_model_execution_receipt_count": 0,
                    "crash_oom_free_execution_count": 0,
                    "scorecard_or_review_count": 0,
                    "runner_command_ready": True,
                    "claim_boundary": (
                        "Large-model runner readiness contract only; runner command and "
                        "resource envelope exist, but there is still no acquired source, "
                        "license approval, checksum, reference output, normalized model, "
                        "execution, crash/OOM-free result, or scorecard evidence."
                    ),
                },
            ),
        ),
        BenchmarkAcquisitionSource(
            source_id="buildingsmart_clean_ifc_samples",
            lanes=("buildingsmart-clean-ifc",),
            source_kind="public_ifc_sample_corpus",
            truth_class="geometry_and_import_truth",
            acquisition_mode="manifested_user_or_ci_download_after_license_review",
            source_url_or_doi=(
                "https://github.com/buildingSMART/Sample-Test-Files/tree/main/"
                "IFC%204.3.2.0%20%28IFC4X3_ADD2%29/PCERT-Sample-Scene"
            ),
            license_status="declared_cc_by_4_0_product_legal_review_pending",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="missing_until_source_acquired",
            expected_output_status="authored_import_health_contracts_pending_execution",
            normalization_status="not_started",
            reference_result_status="not_applicable_geometry_import_truth",
            blockers=(
                "license_review_pending",
                "checksum_missing",
                "import_health_execution_missing",
                "silent_import_loss_gate_not_executed",
            ),
            claim_boundary=(
                "Clean IFC lane policy only; geometry/import truth is not solver accuracy truth "
                "and cannot close numerical benchmark requirements."
            ),
            source_license_receipt_path=(
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_source_license_receipt.json"
            ),
            existing_receipts=(
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase3_buildingsmart_ifc_acquisition_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "selected_file_count": 2,
                    "expected_import_health_contract_count": 2,
                    "import_health_execution_count": 0,
                    "claim_boundary": (
                        "Selected-file acquisition and expected import-health contract only; "
                        "no source checksum, license approval, execution, or Phase 3 credit."
                    ),
                },
            ),
        ),
        BenchmarkAcquisitionSource(
            source_id="buildingsmart_dirty_ifc_samples",
            lanes=("buildingsmart-dirty-ifc",),
            source_kind="public_dirty_ifc_sample_corpus",
            truth_class="negative_import_truth",
            acquisition_mode="manifested_user_or_ci_download_after_license_review",
            source_url_or_doi="https://github.com/buildingsmart-community/Community-Sample-Test-Files",
            license_status="declared_cc_by_4_0_per_file_review_pending",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="missing_until_source_acquired",
            expected_output_status="authored_negative_import_contracts_pending_execution",
            normalization_status="not_started",
            reference_result_status="not_applicable_negative_import_truth",
            blockers=(
                "license_review_pending",
                "checksum_missing",
                "dirty_import_execution_missing",
                "silent_data_loss_negative_gate_not_executed",
            ),
            claim_boundary=(
                "Dirty IFC lane policy only; expected warnings/blocks are authored for "
                "eight community files but must be executed before these cases count toward Phase 3."
            ),
            source_license_receipt_path=(
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_source_license_receipt.json"
            ),
            existing_receipts=(
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "selected_file_count": 8,
                    "expected_negative_import_contract_count": 8,
                    "dirty_import_execution_count": 0,
                    "claim_boundary": (
                        "Selected dirty/import-hardening acquisition and expected negative "
                        "contract only; no source checksum, license approval, execution, "
                        "or Phase 3 credit."
                    ),
                },
            ),
        ),
        BenchmarkAcquisitionSource(
            source_id="ifc_query_and_gui_public_corpus",
            lanes=("ifc-query-and-gui",),
            source_kind="ifc_query_task_corpus",
            truth_class="query_and_gui_task_truth",
            acquisition_mode="task_manifest_after_file_license_review",
            source_url_or_doi="https://doi.org/10.48550/arXiv.2605.01698",
            license_status="paper_attached_dataset_repository_and_per_file_review_required",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="missing_until_sources_acquired",
            expected_output_status="missing_until_query_answers_authored",
            normalization_status="not_started",
            reference_result_status="not_applicable_query_truth",
            blockers=(
                "dataset_repository_url_missing",
                "per_file_license_review_pending",
                "checksum_missing",
                "query_task_manifest_missing",
                "query_expected_answers_missing",
                "gui_task_runner_not_implemented",
                "gui_workflow_coverage_missing",
                "ifc_query_gui_task_execution_missing",
            ),
            claim_boundary=(
                "IFC query/GUI policy only; these tasks measure extraction and UX, "
                "not FEM numerical accuracy."
            ),
            source_license_receipt_path=(
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_source_license_receipt.json"
            ),
            existing_receipts=(
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase3_ifc_query_gui_readiness_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "required_task_source_count": 1,
                    "current_task_source_count": 0,
                    "task_manifest_count": 0,
                    "expected_answer_count": 0,
                    "gui_task_execution_count": 0,
                    "workflow_step_pass_count": 0,
                    "claim_boundary": (
                        "IFC query/GUI readiness contract only; no dataset repository, "
                        "per-file license review, checksums, expected answers, task runner, "
                        "five-step workflow execution, or FEM numerical accuracy evidence."
                    ),
                },
            ),
        ),
        BenchmarkAcquisitionSource(
            source_id="commercial_cross_solver_operator_imports",
            lanes=("commercial-cross-solver",),
            source_kind="operator_supplied_comparison_outputs",
            truth_class="comparison_reference",
            acquisition_mode="operator_attached_import_template_not_bundled",
            source_url_or_doi="operator_supplied:no_public_redistribution",
            license_status="operator_owned_not_redistributable",
            redistribution_allowed=False,
            commercial_use_allowed=False,
            checksum_status="missing_until_operator_files_attached",
            expected_output_status=(
                "authored_import_template_and_operator_contract_pending_reference_outputs"
            ),
            normalization_status="not_started",
            reference_result_status="not_ingested",
            blockers=(
                "operator_reference_package_missing",
                "operator_files_missing",
                "license_or_customer_permission_missing",
                "checksum_missing",
                "operator_reference_ingest_validator_blocked",
                "operator_reference_outputs_missing",
                "two_reference_solver_comparison_not_available",
                "operator_file_checksums_missing",
                "modeling_convention_declarations_missing",
                "modeling_assumption_diagnosis_execution_missing",
                "operator_comparison_trace_rows_missing",
                "commercial_cross_solver_execution_missing",
            ),
            claim_boundary=(
                "Commercial cross-solver lane policy only; commercial results are comparison "
                "references, not absolute truth, and are not bundled."
            ),
            existing_receipts=(
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase4_commercial_comparison_import_template.json"
                    ),
                    "status": "ready",
                    "contract_pass": True,
                    "required_result_field_count": 16,
                    "claim_boundary": (
                        "Template and mapping expectations only; no operator files, "
                        "checksums, commercial execution, or two-reference comparison evidence."
                    ),
                },
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase4_commercial_operator_reference_contract.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "required_reference_solver_count": 2,
                    "current_reference_solver_count": 0,
                    "claim_boundary": (
                        "Operator reference package contract only; no operator files, "
                        "permission, checksums, ingestion, GUI traceability, or two-reference "
                        "comparison evidence."
                    ),
                },
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase4_commercial_operator_reference_ingest_validator.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "validation_scope": (
                        "Operator package shape, permission, two-reference-solver presence, "
                        "modeling convention declarations, and SHA256 coverage."
                    ),
                    "claim_boundary": (
                        "Ingest preflight only; default artifact has no operator package and "
                        "does not run comparisons or close Phase 4."
                    ),
                },
                {
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "phase4_commercial_cross_solver_readiness_receipt.json"
                    ),
                    "status": "blocked",
                    "contract_pass": False,
                    "required_reference_solver_count": 2,
                    "current_reference_solver_count": 0,
                    "operator_package_attached": False,
                    "operator_permission_attached": False,
                    "operator_trace_rows_available": False,
                    "claim_boundary": (
                        "Commercial cross-solver readiness rollup only; no operator files, "
                        "permission, checksums, commercial execution, two-reference comparison, "
                        "or GUI story/member/mode trace rows."
                    ),
                },
            ),
        ),
    ]


def build_phase3_acquisition_plan() -> dict[str, Any]:
    rows = [source.row() for source in phase3_non_seed_acquisition_sources()]
    lanes = sorted({lane for row in rows for lane in row["lanes"]})
    clean_ifc_contract_count = sum(
        receipt.get("selected_file_count", 0)
        for row in rows
        if "buildingsmart-clean-ifc" in row["lanes"]
        for receipt in row["existing_receipts"]
    )
    dirty_ifc_contract_count = sum(
        receipt.get("selected_file_count", 0)
        for row in rows
        if "buildingsmart-dirty-ifc" in row["lanes"]
        for receipt in row["existing_receipts"]
    )
    total_ifc_contract_count = clean_ifc_contract_count + dirty_ifc_contract_count
    remaining_ifc_contract_count = max(
        PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT - total_ifc_contract_count,
        0,
    )
    ifc_import_case_requirement = {
        "minimum_clean_dirty_import_case_count": PHASE3_REQUIRED_IFC_IMPORT_CASE_COUNT,
        "selected_clean_import_contract_count": clean_ifc_contract_count,
        "selected_dirty_import_contract_count": dirty_ifc_contract_count,
        "selected_total_import_contract_count": total_ifc_contract_count,
        "remaining_import_contract_count": remaining_ifc_contract_count,
        "quantity_credit_ready_count": 0,
        "import_health_execution_receipt_path": (
            "implementation/phase1/release_evidence/productization/"
            "phase3_ifc_import_health_execution_receipt.json"
        ),
        "status": "blocked",
        "blocker": "phase3_ifc_import_case_quantity_credit_missing",
        "claim_boundary": (
            "The Phase 3 roadmap requires at least 10 clean/dirty IFC import cases. "
            "Current acquisition evidence contains two clean buildingSMART expected "
            "import-health contracts and eight dirty/negative expected block contracts, "
            "but zero quantity-credit-ready IFC cases."
        ),
    }
    count_blockers = ["phase3_ifc_import_case_quantity_credit_missing"]
    if remaining_ifc_contract_count > 0:
        count_blockers.append("phase3_ifc_import_case_count_below_minimum")
    blockers = sorted(
        {
            *{blocker for row in rows for blocker in row["blockers"]},
            *count_blockers,
        }
    )
    rows_ready = [
        row
        for row in rows
        if row["redistribution_allowed"]
        and row["commercial_use_allowed"]
        and row["checksum_status"] == "ready"
        and row["expected_output_status"] == "ready"
        and row["normalization_status"] == "ready"
    ]
    sample_acquisition_command = {
        "status": "ready",
        "contract_pass": True,
        "command": "python3 scripts/build_phase3_benchmark_acquisition_artifacts.py --json",
        "writes_default_artifact_command": (
            "python3 scripts/build_phase3_benchmark_acquisition_artifacts.py"
        ),
        "downloads_external_data": False,
        "bundles_external_data": False,
        "requires_network": False,
        "scope": (
            "Print or write the Phase 3 acquisition policy, source identities, "
            "blockers, and local/operator action requirements for non-seed benchmark lanes."
        ),
        "remaining_corpus_readiness_blockers": blockers,
        "claim_boundary": (
            "This is a sample acquisition policy command surface only. It does not "
            "download sources, approve licenses, attach checksums, ingest reference "
            "outputs, execute IFC/OpenSees/commercial cases, or close Phase 3."
        ),
    }
    return {
        "schema_version": "phase3-benchmark-acquisition-plan.v1",
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "non_seed_lane_count": len(lanes),
        "non_seed_source_count": len(rows),
        "ready_source_count": len(rows_ready),
        "local_candidate_source_count": sum(1 for row in rows if row["local_candidate_artifacts"]),
        "topology_receipt_source_count": sum(1 for row in rows if row["existing_receipts"]),
        "source_license_receipt_source_count": sum(1 for row in rows if row["source_license_receipt_path"]),
        "sample_acquisition_command": sample_acquisition_command,
        "ifc_import_case_requirement": ifc_import_case_requirement,
        "all_non_seed_lanes_have_acquisition_policy": lanes
        == [
            "buildingsmart-clean-ifc",
            "buildingsmart-dirty-ifc",
            "commercial-cross-solver",
            "ifc-query-and-gui",
            "large-model-performance",
            "opensees-medium",
            "opensees-megatall",
        ],
        "all_non_seed_sources_have_license_checksum_and_expected_outputs": False,
        "lanes": lanes,
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt defines acquisition, license, checksum, expected-output, and "
            "normalization policy for non-seed Phase 3 lanes. It does not download or "
            "bundle upstream data, grant redistribution rights, ingest reference results, "
            "run OpenSees/buildingSMART/commercial/large-model cases, or close Phase 3."
        ),
    }
