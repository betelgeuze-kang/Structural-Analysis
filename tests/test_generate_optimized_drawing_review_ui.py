from __future__ import annotations

import importlib.util
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REQUIRED_PROJECT_PACKAGE_MEMBERS = {
    "visualization/optimized_drawing_review.html": "optimized_drawing_review.html",
    "visualization/optimized_drawing_expert_review.html": "optimized_drawing_expert_review.html",
    "visualization/optimized_drawing_review_summary.json": "optimized_drawing_review_summary.json",
    "visualization/optimized_drawing_expert_review.metadata.json": "optimized_drawing_expert_review.metadata.json",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/generate_optimized_drawing_review_ui.py"
    )
    spec = importlib.util.spec_from_file_location("optimized_drawing_review_ui_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_delivery_contract_fixture(
    tmp_path: Path,
    module,
    *,
    real_drawing_corpus_report_path: Path | None = None,
    model_optimization_intake_queue_path: Path | None = None,
    redacted_manifest_path: Path | None = None,
) -> tuple[Path, Path]:
    release_dir = tmp_path / "release"
    visualization_dir = release_dir / "visualization"
    signing_dir = release_dir / "signing"
    visualization_dir.mkdir(parents=True, exist_ok=True)
    signing_dir.mkdir(parents=True, exist_ok=True)

    project_registry = release_dir / "project_registry.json"
    project_signature = signing_dir / "project_registry.signature.b64"
    project_package = release_dir / "project_package.zip"
    _write_json(project_registry, {"contract_pass": True, "summary": {"package_sha256": "fixture"}})
    project_signature.write_text("U0lHTkFUVVJF\n", encoding="utf-8")
    with zipfile.ZipFile(project_package, "w") as archive:
        archive.writestr("package_manifest.json", "{}")

    source_mgt = visualization_dir / "midas_generator_33.mgt"
    optimized_mgt = visualization_dir / "midas_generator_33.optimized.mgt"
    loadcomb_report = visualization_dir / "midas_generator_33.optimized.loadcomb_roundtrip_report.json"
    diff_json = visualization_dir / "midas_generator_33.optimized.source_output_diff.json"
    diff_txt = visualization_dir / "midas_generator_33.optimized.source_output_diff.txt"
    diff_window_json = visualization_dir / "midas_generator_33.optimized.source_output_diff_window.json"
    diff_window_txt = visualization_dir / "midas_generator_33.optimized.source_output_diff_window.txt"
    midas_gate = visualization_dir / "midas_native_roundtrip_gate_report.json"
    export_report = visualization_dir / "midas_generator_33.optimized.export_report.json"

    source_mgt.write_text("*SOURCE\n", encoding="utf-8")
    optimized_mgt.write_text("*SOURCE\n*OPTIMIZED\n", encoding="utf-8")
    _write_json(loadcomb_report, {"contract_pass": True, "summary": {"combo_count": 1}})
    _write_json(diff_json, {"changed_line_count": 1, "sample_lines": ["+*OPTIMIZED"]})
    diff_txt.write_text("source_output_mgt preview\n", encoding="utf-8")
    _write_json(
        diff_window_json,
        {
            "summary_line": "source_output_mgt window: changed=1",
            "window_rows": [{"member_id": "B-101", "line": "+*OPTIMIZED"}],
            "member_row_indices": {"B-101": [0]},
        },
    )
    diff_window_txt.write_text("MIDAS source vs output diff window\n", encoding="utf-8")
    _write_json(
        midas_gate,
        {
            "contract_pass": True,
            "summary": {
                "summary_line": "roundtrip gate: PASS",
                "ready_count": 1,
                "corpus_case_count": 1,
                "public_native_ready_count": 1,
            },
        },
    )
    _write_json(
        export_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "support_mode": "fixture_supported_changeset",
                "mgt_export_delivery_boundary": "fixture delivery boundary",
                "output_mgt_exists": True,
                "loadcomb_roundtrip_pass": True,
                "loadcomb_combo_count": 1,
                "unsupported_change_count": 0,
                "total_change_count": 1,
                "source_vs_output_diff_summary_line": "source_output_mgt: changed=1",
                "source_vs_output_diff_changed_line_count": 1,
                "source_output_mgt_diff_window_member_row_indices": {"B-101": [0]},
            },
            "artifacts": {
                "source_mgt": str(source_mgt),
                "output_mgt": str(optimized_mgt),
                "loadcomb_roundtrip_report_json": str(loadcomb_report),
                "source_output_mgt_diff_json": str(diff_json),
                "source_output_mgt_diff_preview_txt": str(diff_txt),
                "source_output_mgt_diff_window_json": str(diff_window_json),
                "source_output_mgt_diff_window_preview_txt": str(diff_window_txt),
            },
        },
    )

    viewer_json = visualization_dir / "structural_optimization_viewer.json"
    out_html = visualization_dir / "optimized_drawing_review.html"
    out_summary = visualization_dir / "optimized_drawing_review_summary.json"
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "delivery_contract_fixture",
                "case_title": "Delivery Contract Fixture",
                "mgt_export_report_path": str(export_report),
                "midas_native_roundtrip_gate_report_path": str(midas_gate),
            },
            "baseline_structure": {
                "total_element_count": 2,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "member_locator_rows": [{"member_id": "B-101", "story": "S01"}],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {"member_id": "B-101", "story_band_label": "S01", "p0": [0, 0, 0], "p1": [1, 0, 0]}
                ],
                "after_segments": [
                    {"member_id": "B-101", "story_band_label": "S01", "p0": [0, 0, 0], "p1": [1, 0, 0]}
                ],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "member_type": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -1.0,
                        "constructability_delta_sum": 0.0,
                        "max_dcr_after_max": 0.8,
                    }
                ],
                "story_band_rows": [
                    {
                        "story_band": "S01",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -1.0,
                        "constructability_delta_sum": 0.0,
                        "max_dcr_after_max": 0.8,
                    }
                ],
                "zone_rows": [],
            },
            "artifact_links": {
                "project_registry_report": str(project_registry),
                "project_package_zip": str(project_package),
                "project_registry_signature": str(project_signature),
            },
        },
    )

    module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_expert_review_issue_metadata.json",
        real_drawing_corpus_report_path=real_drawing_corpus_report_path,
        model_optimization_intake_queue_path=model_optimization_intake_queue_path,
        redacted_manifest_path=redacted_manifest_path,
    )
    return out_summary, out_summary.with_name("optimized_drawing_expert_review.metadata.json")


def _assert_delivery_contract_core(payload: dict) -> None:
    archive_contract = payload["export_handoff_contracts"]["archive_handoff_contract"]
    assert archive_contract["pass"] is True
    assert archive_contract["artifact_href_validation_summary"]["pass"] is True
    assert archive_contract["artifact_href_validation_summary"]["missing_required_count"] == 0

    href_validation = payload["artifact_href_validation"]
    assert href_validation["pass"] is True
    assert href_validation["missing_required_count"] == 0
    assert isinstance(href_validation["missing_required_keys"], list)

    story_schedule_rows = payload["story_schedule_rows"]
    assert story_schedule_rows
    for row in story_schedule_rows:
        assert {
            "total_segment_count",
            "renderable_segment_count",
            "focusable_segment_count",
            "invalid_excluded_count",
        } <= set(row)
        assert isinstance(row["total_segment_count"], int)
        assert isinstance(row["renderable_segment_count"], int)
        assert isinstance(row["focusable_segment_count"], int)
        assert isinstance(row["invalid_excluded_count"], int)

    evidence_summary = payload["representative_evidence_completeness_summary"]
    assert {"total", "complete", "partial", "missing", "missing_evidence_field_counts"} <= set(evidence_summary)
    assert isinstance(evidence_summary["total"], int)
    assert isinstance(evidence_summary["complete"], int)
    assert isinstance(evidence_summary["partial"], int)
    assert isinstance(evidence_summary["missing"], int)
    assert evidence_summary["total"] == (
        evidence_summary["complete"] + evidence_summary["partial"] + evidence_summary["missing"]
    )
    assert set(evidence_summary["missing_evidence_field_counts"]) == {
        "ai_reason",
        "review_handoff_summary",
        "source_output_diff_focus",
        "linked_diff_row_count",
    }
    assert all(isinstance(count, int) for count in evidence_summary["missing_evidence_field_counts"].values())


def test_real_drawing_private_corpus_registers_release_safe_webviewer_summary(tmp_path: Path) -> None:
    module = _load_module()
    corpus_dir = tmp_path / "real_drawing_fixture"
    report_path = corpus_dir / "real_drawing_private_corpus_report.json"
    queue_path = corpus_dir / "model_optimization_intake_queue.json"
    manifest_path = corpus_dir / "redacted_manifest.json"
    forbidden_tokens = [
        "SHOULD_NOT_LEAK",
        "source_url",
        "private_path",
        "source_private_manifest",
        "source_intake_queue",
        "source_redacted_manifest",
        "zip_model_member_names_sample",
        "release_rows",
        "derived_hrefs",
        "tmp/real_drawing_private_corpus",
    ]

    _write_json(
        report_path,
        {
            "schema_version": "real_drawing_private_corpus_report.v1",
            "contract_pass": True,
            "reason_code": "PASS",
            "generated_at": "2026-05-06T00:00:00+00:00",
            "source_intake_queue": "SHOULD_NOT_LEAK_QUEUE_PATH",
            "source_redacted_manifest": "SHOULD_NOT_LEAK_MANIFEST_PATH",
            "manifest_summary": {
                "project_count": 2,
                "file_count": 4,
                "total_mb": 12.5,
                "drawing_review_candidate_count": 2,
                "drawing_sheet_candidate_count": 9,
                "model_optimization_candidate_count": 3,
                "model_optimization_asset_count": 3,
                "private_only": True,
                "raw_redistribution_allowed": False,
                "raw_redistribution_allowed_count": 0,
                "release_surface_allowed": False,
                "release_surface_allowed_count": 0,
                "file_type_counts": {".ifc": 1, ".mgt": 1, ".zip": 1, ".pdf": 1},
                "license_basis": "Redacted metadata only.",
                "storage_boundary": "private_corpus_only",
            },
            "queue_summary": {
                "candidate_file_count": 3,
                "optimized_drawing_generation_ready_count": 2,
                "optimized_drawing_generation_ready_model_asset_count": 3,
                "solver_exact_ready_count": 1,
                "solver_graph_ready_count": 1,
                "proxy_or_preview_ready_count": 1,
                "ifc_proxy_graph_ready_count": 1,
                "archive_hard_tier_ready_count": 0,
                "archive_hard_tier_blocked_count": 1,
                "ready_node_count_total": 12,
                "ready_element_count_total": 10,
                "route_counts": {"midas_mgt_direct_parser": 1, "ifc_to_structural_graph_adapter": 1},
                "status_counts": {"solver_graph_ready": 1, "ifc_proxy_graph_ready": 1},
            },
            "summary": {"remaining_blocker_count": 1},
            "consistency": {
                "counts_consistent": True,
                "surface_safe": True,
                "tier_acceptance_all_pass": True,
                "release_surface_allowed_count_zero": True,
                "raw_redistribution_allowed_false": True,
                "input_artifact_freshness_pass": True,
            },
        },
    )
    _write_json(
        queue_path,
        {
            "contract_pass": True,
            "summary": {
                "candidate_file_count": 3,
                "optimized_drawing_generation_ready_count": 2,
                "optimized_drawing_generation_ready_model_asset_count": 3,
                "solver_exact_ready_count": 1,
                "proxy_or_preview_ready_count": 1,
            },
            "queue": [
                {
                    "file_id": "SHOULD_NOT_LEAK_FILE_ID",
                    "file_name": "SHOULD_NOT_LEAK_MODEL.mgt",
                    "source_url": "https://SHOULD_NOT_LEAK.example/model.mgt",
                    "private_path": "/home/SHOULD_NOT_LEAK/private/model.mgt",
                    "source_private_manifest": "SHOULD_NOT_LEAK_PRIVATE_MANIFEST",
                    "zip_model_member_names_sample": ["SHOULD_NOT_LEAK_MEMBER.mgb"],
                    "solver_graph_model_json": "tmp/real_drawing_private_corpus/SHOULD_NOT_LEAK/model.json",
                    "optimization_route": "midas_mgt_direct_parser",
                    "optimization_status": "solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                    "model_asset_count": 1,
                    "node_count": 7,
                    "element_count": 6,
                },
                {
                    "file_id": "SHOULD_NOT_LEAK_IFC_ID",
                    "file_name": "SHOULD_NOT_LEAK.ifc",
                    "source_url": "https://SHOULD_NOT_LEAK.example/model.ifc",
                    "ifc_proxy_graph_json": "tmp/real_drawing_private_corpus/SHOULD_NOT_LEAK/ifc.graph.json",
                    "optimization_route": "ifc_to_structural_graph_adapter",
                    "optimization_status": "ifc_proxy_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": False,
                    "model_asset_count": 2,
                    "proxy_node_count": 5,
                    "proxy_edge_count": 4,
                },
            ],
        },
    )
    _write_json(
        manifest_path,
        {
            "contract_pass": True,
            "policy": {
                "license_basis": "Redacted metadata only.",
                "raw_redistribution_allowed": False,
                "release_surface_allowed": False,
                "storage_boundary": "private_corpus_only",
            },
            "summary": {
                "project_count": 2,
                "file_count": 4,
                "drawing_sheet_candidate_count": 9,
                "model_optimization_candidate_count": 3,
                "private_only": True,
                "raw_redistribution_allowed_count": 0,
                "release_surface_allowed_count": 0,
            },
            "projects": [
                {
                    "project_id": "SHOULD_NOT_LEAK_PROJECT",
                    "files": [
                        {
                            "file_name": "SHOULD_NOT_LEAK.pdf",
                            "source_url": "https://SHOULD_NOT_LEAK.example/drawing.pdf",
                            "private_path": "/home/SHOULD_NOT_LEAK/private/drawing.pdf",
                        }
                    ],
                }
            ],
        },
    )

    summary_path, _ = _write_delivery_contract_fixture(
        tmp_path,
        module,
        real_drawing_corpus_report_path=report_path,
        model_optimization_intake_queue_path=queue_path,
        redacted_manifest_path=manifest_path,
    )
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    corpus_payload = summary_payload["real_drawing_private_corpus"]
    assert corpus_payload["registered"] is True
    assert corpus_payload["release_surface"] == "release_safe_metadata_only"
    assert corpus_payload["summary"]["optimized_drawing_generation_ready_count"] == 2
    assert corpus_payload["summary"]["ready_model_asset_count"] == 3
    assert corpus_payload["summary"]["solver_exact_ready_count"] == 1
    assert corpus_payload["policy"]["surface_safe"] is True
    assert corpus_payload["policy"]["release_surface_allowed_count"] == 0
    assert corpus_payload["policy"]["raw_redistribution_allowed_count"] == 0

    html_text = summary_path.with_name("optimized_drawing_review.html").read_text(encoding="utf-8")
    expert_html_text = summary_path.with_name("optimized_drawing_expert_review.html").read_text(encoding="utf-8")
    assert "Real drawing corpus" in html_text
    assert "Corpus R00" in html_text
    assert "2/3" in html_text
    assert "Real drawing corpus" in expert_html_text

    combined_output = "\n".join([summary_path.read_text(encoding="utf-8"), html_text, expert_html_text])
    for token in forbidden_tokens:
        assert token not in combined_output


def _flatten_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _flatten_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_dicts(child)


def _dict_text(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _sha256_values(value) -> list[str]:
    if isinstance(value, dict):
        values = [
            str(child)
            for key, child in value.items()
            if "sha256" in str(key).lower() and not isinstance(child, (dict, list))
        ]
        for child in value.values():
            values.extend(_sha256_values(child))
        return values
    if isinstance(value, list):
        values = []
        for child in value:
            values.extend(_sha256_values(child))
        return values
    return []


def _find_project_package_contract(payload: dict) -> dict:
    candidate_paths = [
        ("package_membership_contract", payload.get("package_membership_contract")),
        ("package_freshness_contract", payload.get("package_freshness_contract")),
        ("archive_handoff_contract", payload.get("archive_handoff_contract")),
        (
            "export_handoff_contracts.archive_handoff_contract",
            payload.get("export_handoff_contracts", {}).get("archive_handoff_contract", {}),
        ),
    ]
    for _, candidate in candidate_paths:
        if not isinstance(candidate, dict):
            continue
        candidate_dicts = list(_flatten_dicts(candidate))
        candidate_text = _dict_text(candidate)
        if (
            "project_package" in candidate_text
            and all(member_name in candidate_text for member_name in REQUIRED_PROJECT_PACKAGE_MEMBERS.values())
            and any("sha256" in _dict_text(row) for row in candidate_dicts)
        ):
            return candidate
    raise AssertionError(
        "release payload must expose project_package freshness/membership contract "
        "with required optimized drawing members and sha256 receipts"
    )


def _find_project_package_membership_contract(payload: dict) -> dict:
    contract = _find_project_package_contract(payload)
    for row in _flatten_dicts(contract):
        if {
            "package_ready",
            "package_membership_status",
            "missing_package_member_count",
            "artifact_rows",
        } <= set(row):
            return row
    raise AssertionError("project_package membership contract must expose package readiness fields")


def _project_package_path(payload: dict, *, release_visualization_dir: Path) -> Path:
    membership_contract = _find_project_package_membership_contract(payload)
    if membership_contract.get("project_package_path"):
        return Path(membership_contract["project_package_path"])

    project_package_href = str(payload.get("project_package_href") or "")
    archive_hrefs = payload.get("export_handoff_contracts", {}).get("archive_handoff_contract", {}).get("hrefs", {})
    if not project_package_href:
        project_package_href = str(
            membership_contract.get("project_package_href") or archive_hrefs.get("project_package_zip_href") or ""
        )
    return (release_visualization_dir / project_package_href).resolve()


def _assert_project_package_freshness_contract(payload: dict, *, release_visualization_dir: Path) -> None:
    contract = _find_project_package_contract(payload)
    membership_contract = _find_project_package_membership_contract(payload)
    contract_text = _dict_text(contract)
    project_package_href = str(payload.get("project_package_href") or "")
    archive_hrefs = payload.get("export_handoff_contracts", {}).get("archive_handoff_contract", {}).get("hrefs", {})
    if not project_package_href:
        project_package_href = str(contract.get("project_package_href") or archive_hrefs.get("project_package_zip_href") or "")

    assert project_package_href == "../project_package.zip"
    assert archive_hrefs.get("project_package_zip_href") == project_package_href
    assert project_package_href in contract_text

    if "pass" in contract:
        assert contract["pass"] is True

    assert membership_contract["package_ready"] is True
    assert membership_contract["package_membership_status"] == "packaged"
    assert membership_contract["missing_package_member_count"] == 0

    contract_rows = list(_flatten_dicts(contract))
    for package_member, artifact_name in REQUIRED_PROJECT_PACKAGE_MEMBERS.items():
        artifact_path = release_visualization_dir / artifact_name
        expected_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        matching_rows = [
            row
            for row in contract_rows
            if artifact_name in _dict_text(row)
            and "sha256" in _dict_text(row).lower()
        ]

        assert package_member in contract_text
        assert matching_rows, f"missing package freshness row for {artifact_name}"
        assert any(str(row.get("exists", row.get("present", True))).lower() != "false" for row in matching_rows)
        if artifact_name.endswith(".html"):
            assert any(expected_sha256 in _dict_text(row) for row in matching_rows)

        sha256_values = [value for row in matching_rows for value in _sha256_values(row)]
        assert any(SHA256_RE.match(value) for value in sha256_values)

    membership_rows = [
        row
        for row in contract_rows
        if row.get("package_member") in REQUIRED_PROJECT_PACKAGE_MEMBERS
        and row.get("artifact_name") in REQUIRED_PROJECT_PACKAGE_MEMBERS.values()
    ]
    assert len(membership_rows) == len(REQUIRED_PROJECT_PACKAGE_MEMBERS)
    assert all(row.get("package_member_status") == "packaged" for row in membership_rows)


def _assert_project_package_zip_members(payload: dict, *, release_visualization_dir: Path) -> None:
    package_path = _project_package_path(payload, release_visualization_dir=release_visualization_dir)
    assert package_path.exists()

    with zipfile.ZipFile(package_path) as project_package:
        member_names = set(project_package.namelist())
        assert set(REQUIRED_PROJECT_PACKAGE_MEMBERS) <= member_names

        for package_member, artifact_name in REQUIRED_PROJECT_PACKAGE_MEMBERS.items():
            artifact_path = release_visualization_dir / artifact_name
            member_bytes = project_package.read(package_member)
            assert member_bytes
            if artifact_name.endswith(".html"):
                assert hashlib.sha256(member_bytes).hexdigest() == hashlib.sha256(artifact_path.read_bytes()).hexdigest()


def test_compact_3d_after_segment_preserves_nullable_metrics_and_contract_summary(tmp_path: Path) -> None:
    module = _load_module()

    missing_metric_segment = module._compact_3d_after_segment(
        {
            "member_id": "NO-METRIC",
            "cost_delta": "",
            "constructability_delta": "",
            "max_dcr_after": "",
            "linked_diff_row_count": None,
            "p0": [0, 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert missing_metric_segment["cost_delta"] is None
    assert missing_metric_segment["constructability_delta"] is None
    assert missing_metric_segment["max_dcr_after"] is None
    assert missing_metric_segment["linked_diff_row_count"] is None

    string_metric_segment = module._compact_3d_after_segment(
        {
            "member_id": "STRING-METRIC",
            "cost_delta": "-2.5",
            "constructability_delta": "0.125",
            "max_dcr_after": "0.92",
            "linked_diff_row_count": "3",
            "p0": [0, 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert string_metric_segment["cost_delta"] == -2.5
    assert string_metric_segment["constructability_delta"] == 0.125
    assert string_metric_segment["max_dcr_after"] == 0.92
    assert string_metric_segment["linked_diff_row_count"] == 3.0

    zero_metric_segment = module._compact_3d_after_segment(
        {
            "member_id": "ZERO-METRIC",
            "cost_delta": 0,
            "constructability_delta": 0,
            "max_dcr_after": 0,
            "linked_diff_row_count": 0,
            "p0": [0, 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert zero_metric_segment["cost_delta"] == 0.0
    assert zero_metric_segment["constructability_delta"] == 0.0
    assert zero_metric_segment["max_dcr_after"] == 0.0
    assert zero_metric_segment["linked_diff_row_count"] == 0.0

    viewer_payload = {
        "interactive_3d": {
            "after_segments": [
                {
                    "member_id": "NO-METRIC",
                    "cost_delta": "",
                    "constructability_delta": "",
                    "max_dcr_after": "",
                    "linked_diff_row_count": None,
                    "p0": [0, 0, 0],
                    "p1": [1, 1, 1],
                },
                {
                    "member_id": "STRING-METRIC",
                    "cost_delta": "-2.5",
                    "constructability_delta": "0.125",
                    "max_dcr_after": "0.92",
                    "linked_diff_row_count": "3",
                    "p0": [0, 0, 0],
                    "p1": [1, 1, 1],
                },
            ],
        }
    }
    payload = module._build_3d_payload(viewer_payload, viewer_json_path=tmp_path / "viewer.json")

    assert payload["interactive_3d_payload_contract_version"]
    assert payload["nullable_metric_fields"] == [
        "cost_delta",
        "constructability_delta",
        "max_dcr_after",
        "linked_diff_row_count",
    ]
    assert "ai_reason" in payload["evidence_field_names"]
    assert "review_handoff_summary" in payload["evidence_field_names"]
    assert payload["after_segment_contract_validation"] == {
        "after_segment_count": 2,
        "compact_after_segment_count": 2,
        "after_segment_count_matches": True,
        "segments_with_all_contract_fields": 2,
    }
    assert payload["after_segments"][0]["linked_diff_row_count"] is None


def test_compact_3d_segments_expose_coordinate_contract_diagnostics(tmp_path: Path) -> None:
    module = _load_module()

    actual_origin_segment = module._compact_3d_baseline_segment(
        {
            "member_id": "ORIGIN",
            "p0": [0, 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert actual_origin_segment["p0"] == [0.0, 0.0, 0.0]
    assert actual_origin_segment["coordinate_valid"] is True
    assert actual_origin_segment["coordinate_status"] == "valid"
    assert actual_origin_segment["coordinate_fallback_fields"] == []
    assert actual_origin_segment["coordinate_fallback_provenance"] == []
    assert actual_origin_segment["coordinate_fallback_diagnostics"] == {}

    string_numeric_segment = module._compact_3d_after_segment(
        {
            "member_id": "STRING-NUMERIC",
            "p0": ["0", "1.25", "-2"],
            "p1": ["3", "4.5", "6"],
        }
    )
    assert string_numeric_segment["p0"] == [0.0, 1.25, -2.0]
    assert string_numeric_segment["p1"] == [3.0, 4.5, 6.0]
    assert string_numeric_segment["coordinate_valid"] is True

    missing_p0_segment = module._compact_3d_after_segment(
        {
            "member_id": "MISSING-P0",
            "p1": [1, 1, 1],
        }
    )
    assert missing_p0_segment["p0"] == [0.0, 0.0, 0.0]
    assert missing_p0_segment["coordinate_valid"] is False
    assert missing_p0_segment["coordinate_status"] == "fallback:p0"
    assert missing_p0_segment["coordinate_fallback_fields"] == ["p0"]
    assert missing_p0_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "missing"
    assert missing_p0_segment["coordinate_fallback_provenance"][0]["reason"] == "missing"

    short_p0_segment = module._compact_3d_after_segment(
        {
            "member_id": "SHORT-P0",
            "p0": [0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert short_p0_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "short"

    bool_p0_segment = module._compact_3d_after_segment(
        {
            "member_id": "BOOL-P0",
            "p0": [True, 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert bool_p0_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "bool"

    bad_string_segment = module._compact_3d_after_segment(
        {
            "member_id": "BAD-STRING",
            "p0": ["bad", 0, 0],
            "p1": [1, 1, 1],
        }
    )
    assert bad_string_segment["coordinate_status"] == "fallback:p0"
    assert bad_string_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "non_numeric"

    nan_inf_segment = module._compact_3d_after_segment(
        {
            "member_id": "NAN-INF",
            "p0": [math.nan, 0, 0],
            "p1": [1, float("inf"), 1],
        }
    )
    assert nan_inf_segment["coordinate_valid"] is False
    assert nan_inf_segment["coordinate_status"] == "fallback:p0,p1"
    assert nan_inf_segment["coordinate_fallback_fields"] == ["p0", "p1"]
    assert nan_inf_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"] == {
        "p0": "non_finite",
        "p1": "non_finite",
    }
    assert nan_inf_segment["coordinate_fallback_diagnostics"]["p0"]["raw_sample"][0] == "nan"
    assert nan_inf_segment["coordinate_fallback_diagnostics"]["p1"]["raw_sample"][1] == "inf"

    upstream_invalid_segment = module._compact_3d_after_segment(
        {
            "member_id": "UPSTREAM-INVALID",
            "p0": [0, 0, 0],
            "p1": [1, 1, 1],
            "coordinate_valid": False,
            "coordinate_status": "fallback:pre_normalized",
            "coordinate_fallback_fields": ["pre_normalized"],
            "coordinate_fallback_provenance": [
                {"endpoint": "p0", "field": "p0", "reason": "upstream_pre_fallback", "source": "upstream", "raw_value": math.inf}
            ],
            "coordinate_fallback_diagnostics": {
                "endpoint_reasons": {"p0": "upstream_pre_fallback"},
                "raw_sample": [math.nan, 0, 0],
                "raw_shapes": {"p0": {"type": "list", "length": 3}},
            },
        }
    )
    assert upstream_invalid_segment["p0"] == [0.0, 0.0, 0.0]
    assert upstream_invalid_segment["coordinate_valid"] is False
    assert upstream_invalid_segment["coordinate_status"] == "fallback:pre_normalized"
    assert upstream_invalid_segment["coordinate_fallback_fields"] == ["pre_normalized"]
    assert upstream_invalid_segment["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "upstream_pre_fallback"
    assert upstream_invalid_segment["coordinate_fallback_diagnostics"]["raw_sample"][0] == "nan"
    assert upstream_invalid_segment["coordinate_fallback_provenance"][0]["source"] == "upstream"
    assert upstream_invalid_segment["coordinate_fallback_provenance"][0]["raw_value"] == "inf"

    payload = module._build_3d_payload(
        {
            "interactive_3d": {
                "baseline_segments": [
                    {"member_id": "ORIGIN", "p0": [0, 0, 0], "p1": [1, 1, 1]},
                    {"member_id": "BASE-STRING", "p0": ["2", "3", "4"], "p1": ["5", "6", "7"]},
                ],
                "after_segments": [
                    {"member_id": "MISSING-P0", "p1": [1, 1, 1]},
                    {"member_id": "STRING-NUMERIC", "p0": ["0", "1.25", "-2"], "p1": ["3", "4.5", "6"]},
                    {"member_id": "BAD-STRING", "p0": ["bad", 0, 0], "p1": [1, 1, 1]},
                    {"member_id": "NAN", "p0": [math.nan, 0, 0], "p1": [1, 1, 1]},
                    {"member_id": "INF", "p0": [0, 0, 0], "p1": [1, float("inf"), 1]},
                    {
                        "member_id": "UPSTREAM-INVALID",
                        "p0": [8, 8, 8],
                        "p1": [9, 9, 9],
                        "coordinate_valid": False,
                        "coordinate_status": "fallback:pre_normalized",
                        "coordinate_fallback_fields": ["pre_normalized"],
                        "coordinate_fallback_diagnostics": {"endpoint_reasons": {"p1": "upstream_pre_fallback"}},
                        "coordinate_fallback_provenance": [{"endpoint": "p1", "field": "p1", "reason": "upstream_pre_fallback", "source": "upstream"}],
                    },
                ],
            }
        },
        viewer_json_path=tmp_path / "viewer.json",
    )

    validation = payload["coordinate_contract_validation"]
    assert validation["baseline_segment_count"] == 2
    assert validation["after_segment_count"] == 6
    assert validation["baseline_invalid_coordinate_count"] == 0
    assert validation["after_invalid_coordinate_count"] == 5
    assert validation["invalid_coordinate_count"] == 5
    assert validation["coordinate_fallback_field_count"] == 5
    assert validation["coordinate_contract_valid"] is False
    assert validation["invalid_coordinate_preview"][0]["lane"] == "after"
    assert validation["invalid_coordinate_preview"][0]["member_id"] == "MISSING-P0"
    assert validation["invalid_coordinate_preview"][0]["coordinate_fallback_diagnostics"]["endpoint_reasons"]["p0"] == "missing"
    assert validation["invalid_coordinate_details"]["after"][0]["coordinate_status"] == "fallback:p0"
    assert validation["after_invalid_coordinate_preview_limit"] == 8
    assert payload["coordinate_contract_version"] == "optimized-review-3d-coordinate-v1"
    assert payload["valid_geometry_available"] is True
    assert payload["no_valid_geometry"] is False
    assert payload["valid_point_count"] == 6
    assert payload["valid_segment_count"] == 3
    assert payload["invalid_excluded_count"] == 5
    assert validation["valid_geometry_available"] is True
    assert validation["valid_point_count"] == 6
    assert validation["valid_segment_count"] == 3
    assert validation["invalid_excluded_count"] == 5

    fallback_excluded_payload = module._build_3d_payload(
        {
            "interactive_3d": {
                "baseline_segments": [
                    {"member_id": "VALID-FAR", "p0": [100, 100, 100], "p1": [110, 110, 110]},
                ],
                "after_segments": [
                    {"member_id": "INVALID-ORIGIN-FALLBACK", "p0": ["bad", 0, 0], "p1": [0, 0, 0]},
                ],
            }
        },
        viewer_json_path=tmp_path / "viewer.json",
    )
    assert fallback_excluded_payload["after_segments"][0]["coordinate_valid"] is False
    assert fallback_excluded_payload["extent"] == {
        "min_x": 100.0,
        "max_x": 110.0,
        "min_y": 100.0,
        "max_y": 110.0,
        "min_z": 100.0,
        "max_z": 110.0,
    }
    assert all(row["value"] >= 100.0 for row in fallback_excluded_payload["axis_refs"]["z"])

    all_invalid_payload = module._build_3d_payload(
        {
            "interactive_3d": {
                "baseline_segments": [
                    {"member_id": "BAD-BASE", "story_band_label": "S01", "p0": ["bad", 0, 0], "p1": [1, 1, 1]},
                ],
                "after_segments": [
                    {"member_id": "BAD-AFTER", "story_band_label": "S01", "p0": [0, 0, 0], "p1": [1, float("inf"), 1]},
                ],
            }
        },
        viewer_json_path=tmp_path / "viewer.json",
    )
    all_invalid_validation = all_invalid_payload["coordinate_contract_validation"]
    assert all_invalid_payload["valid_geometry_available"] is False
    assert all_invalid_payload["no_valid_geometry"] is True
    assert all_invalid_payload["geometry_status"] == "no_valid_geometry"
    assert all_invalid_payload["extent_source"] == "no_valid_geometry"
    assert all_invalid_payload["extent_status"] == "no_valid_geometry"
    assert all_invalid_payload["axis_ref_source_mode"] == "no_valid_geometry"
    assert all_invalid_payload["valid_point_count"] == 0
    assert all_invalid_payload["valid_segment_count"] == 0
    assert all_invalid_payload["invalid_excluded_count"] == 2
    assert all_invalid_validation["valid_geometry_available"] is False
    assert all_invalid_validation["no_valid_geometry"] is True
    assert all_invalid_validation["geometry_status"] == "no_valid_geometry"
    assert all_invalid_validation["invalid_excluded_count"] == 2


def test_write_review_artifacts_generates_html_summary_and_svg_assets(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    export_report = tmp_path / "midas_generator_33.optimized.export_report.json"
    roundtrip_gate_report = tmp_path / "midas_native_roundtrip_gate_report.json"
    source_mgt = tmp_path / "midas_generator_33.mgt"
    output_mgt = tmp_path / "midas_generator_33.optimized.mgt"
    loadcomb_preview = tmp_path / "midas_generator_33.optimized.loadcomb_preview.mgt"
    loadcomb_roundtrip_report = tmp_path / "midas_generator_33.optimized.loadcomb_roundtrip_report.json"
    source_output_diff_json = tmp_path / "midas_generator_33.optimized.source_output_diff.json"
    source_output_diff_preview = tmp_path / "midas_generator_33.optimized.source_output_diff.txt"
    source_output_diff_window_json = tmp_path / "midas_generator_33.optimized.source_output_diff_window.json"
    source_output_diff_window_preview = tmp_path / "midas_generator_33.optimized.source_output_diff_window.txt"
    source_mgt.write_text("*UNIT\n*NODE\n1, 0.0, 0.0, 0.0\n*ENDDATA\n", encoding="utf-8")
    output_mgt.write_text("*UNIT\n*ENDDATA\n", encoding="utf-8")
    loadcomb_preview.write_text("*COMBINATION\n1,DEAD,1.0\n", encoding="utf-8")
    source_output_diff_preview.write_text(
        "source_output_mgt preview\nsource=source.mgt\noutput=optimized.mgt\n~ changed line\n+ inserted line\n",
        encoding="utf-8",
    )
    _write_json(
        source_output_diff_json,
        {
            "summary_line": "source_output_mgt: changed=6 | added=2 | removed=0 | source_lines=37250 | output_lines=37281",
            "sample_lines": ["~ changed line", "+ inserted line"],
        },
    )
    _write_json(
        source_output_diff_window_json,
        {
            "summary_line": "source_output_mgt window: changed=6 | added=2 | removed=0 | window_count=3",
            "member_row_indices": {"B-101": [0], "C-201": [1], "D-301": [2]},
            "row_ids": ["mgt-diff-row-0000", "mgt-diff-row-0001", "mgt-diff-row-0002"],
            "window_rows": [
                {
                    "kind": "replace",
                    "source_line_number": 1,
                    "output_line_number": 1,
                    "source_line": "B-101, BEAM, 1, 2, 3",
                    "output_line": "B-101, BEAM, 1, 2, 4",
                    "candidate_member_ids": ["B-101"],
                    "candidate_section_ids": ["S05"],
                    "candidate_card_ids": ["B-101"],
                    "geometry_bridge_member_ids": ["B-101"],
                    "exact_member_id_match": True,
                    "row_index": 0,
                    "row_id": "mgt-diff-row-0000",
                    "search_tokens": ["b-101", "beam", "1", "2", "3", "4"],
                    "search_text": "b-101 beam 1 2 3 4",
                },
                {
                    "kind": "replace",
                    "source_line_number": 2,
                    "output_line_number": 2,
                    "source_line": "C-201, COLUMN, 1, 3, 4",
                    "output_line": "C-201, COLUMN, 1, 3, 5",
                    "candidate_member_ids": ["C-201"],
                    "candidate_section_ids": ["S02"],
                    "candidate_card_ids": ["C-201"],
                    "geometry_bridge_member_ids": ["C-201"],
                    "exact_member_id_match": True,
                    "row_index": 1,
                    "row_id": "mgt-diff-row-0001",
                    "search_tokens": ["c-201", "column", "1", "3", "4", "5"],
                    "search_text": "c-201 column 1 3 4 5",
                },
                {
                    "kind": "insert",
                    "source_line_number": None,
                    "output_line_number": 3,
                    "source_line": "",
                    "output_line": "D-301, WALL, 2, 4, 5",
                    "candidate_member_ids": ["D-301"],
                    "candidate_section_ids": ["S07"],
                    "candidate_card_ids": ["D-301"],
                    "geometry_bridge_member_ids": ["D-301"],
                    "exact_member_id_match": True,
                    "row_index": 2,
                    "row_id": "mgt-diff-row-0002",
                    "search_tokens": ["d-301", "wall", "2", "4", "5"],
                    "search_text": "d-301 wall 2 4 5",
                },
            ],
        },
    )
    source_output_diff_window_preview.write_text(
        "MIDAS source vs output diff window\nwindow_count=3\nreplace S:1 O:1\n",
        encoding="utf-8",
    )
    _write_json(loadcomb_roundtrip_report, {"pass": True, "exact_entry_row_coverage": 1.0, "raw_combo_count": 8})
    _write_json(
        export_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": "bounded MIDAS export completed",
            "summary": {
                "support_mode": "native_authoring_supported_changeset",
                "output_mgt_exists": True,
                "loadcomb_roundtrip_pass": True,
                "loadcomb_combo_count": 8,
                "loadcomb_roundtrip_summary_line": "MGT export LOADCOMB roundtrip: ok | entry_row_coverage=1.00 | combos=8",
                "mgt_export_delivery_boundary": "direct_patch=beam_section=1 | sidecar=none",
                "native_authoring_summary_line": "supported=36/36 | direct_patch=25 | zero_touch_verified=11 | manual_sidecar=0 | unsupported=0",
                "source_output_mgt_diff_available": True,
                "source_output_mgt_summary_line": "source_output_mgt: changed=6 | added=2 | removed=0 | source_lines=37250 | output_lines=37281",
                "source_output_mgt_source_meaningful_line_count": 37250,
                "source_output_mgt_output_meaningful_line_count": 37281,
                "source_output_mgt_changed_line_count": 6,
                "source_output_mgt_added_line_count": 2,
                "source_output_mgt_removed_line_count": 0,
                "source_output_mgt_total_delta_count": 8,
                "source_output_mgt_diff_json_exists": True,
                "source_output_mgt_diff_preview_exists": True,
                "source_output_mgt_diff_window_json_exists": True,
                "source_output_mgt_diff_window_preview_exists": True,
                "source_output_mgt_verification_receipt_line": "source_output_mgt diff receipt: ok | json=yes | txt=yes | changed=6 | added=2 | removed=0",
                "source_output_mgt_diff_sample_lines": [
                    "~ S:13156 O:13156 | src=1166, PLATE , 4, 6, 3634, 3625, 3624, 3148, 4, 0 | out=1166, PLATE, 13, 6, 3634, 3625, 3624, 3148, 4, 0",
                    "+ O:14500 | out=9999, BEAM, 31, 370, 24, 613, 0, 0",
                ],
                "source_output_mgt_diff_window_search_tokens": ["b-101", "c-201", "d-301", "beam", "column", "wall"],
                "source_output_mgt_diff_window_member_ids": ["B-101", "C-201", "D-301"],
                "source_output_mgt_diff_window_section_ids": ["S05", "S02", "S07"],
                "source_output_mgt_diff_window_member_row_indices": {"B-101": [0], "C-201": [1], "D-301": [2]},
                "source_output_mgt_diff_window_row_ids": [
                    "mgt-diff-row-0000",
                    "mgt-diff-row-0001",
                    "mgt-diff-row-0002",
                ],
                "source_vs_output_diff_summary_line": "source_vs_output_mgt: changed=6 | added=2 | removed=0 | sample_rows=2 | whitespace_ignored=yes",
                "source_vs_output_diff_changed_line_count": 6,
                "source_vs_output_diff_added_line_count": 2,
                "source_vs_output_diff_removed_line_count": 0,
                "source_vs_output_diff_sample_count": 2,
                "source_vs_output_source_line_count": 37250,
                "source_vs_output_output_line_count": 37281,
                "source_vs_output_diff_sample_rows": [
                    {
                        "kind": "replace",
                        "source_line_number": 13156,
                        "output_line_number": 13156,
                        "source_line": "1166, PLATE, 4, 6, 3634, 3625, 3624, 3148, 4, 0",
                        "output_line": "1166, PLATE, 13, 6, 3634, 3625, 3624, 3148, 4, 0",
                        "candidate_member_ids": ["1166"],
                        "geometry_bridge_member_ids": ["1166"],
                        "exact_member_id_match": True,
                        "search_tokens": ["1166", "plate", "13"],
                        "search_text": "1166 plate 13",
                    },
                    {
                        "kind": "insert",
                        "source_line_number": None,
                        "output_line_number": 14500,
                        "source_line": "",
                        "output_line": "9999, BEAM, 31, 370, 24, 613, 0, 0",
                        "candidate_member_ids": ["9999"],
                        "geometry_bridge_member_ids": ["9999"],
                        "exact_member_id_match": True,
                        "search_tokens": ["9999", "beam", "31"],
                        "search_text": "9999 beam 31",
                    },
                ],
                "source_vs_output_diff_window_rows": [
                    {
                        "kind": "replace",
                        "source_line_number": 1,
                        "output_line_number": 1,
                        "source_line": "B-101, BEAM, 1, 2, 3",
                        "output_line": "B-101, BEAM, 1, 2, 4",
                        "candidate_member_ids": ["B-101"],
                        "candidate_section_ids": ["S05"],
                        "candidate_card_ids": ["B-101"],
                        "geometry_bridge_member_ids": ["B-101"],
                        "exact_member_id_match": True,
                        "row_index": 0,
                        "row_id": "mgt-diff-row-0000",
                        "search_tokens": ["b-101", "beam", "1", "2", "3", "4"],
                        "search_text": "b-101 beam 1 2 3 4",
                    },
                    {
                        "kind": "replace",
                        "source_line_number": 2,
                        "output_line_number": 2,
                        "source_line": "C-201, COLUMN, 1, 3, 4",
                        "output_line": "C-201, COLUMN, 1, 3, 5",
                        "candidate_member_ids": ["C-201"],
                        "candidate_section_ids": ["S02"],
                        "candidate_card_ids": ["C-201"],
                        "geometry_bridge_member_ids": ["C-201"],
                        "exact_member_id_match": True,
                        "row_index": 1,
                        "row_id": "mgt-diff-row-0001",
                        "search_tokens": ["c-201", "column", "1", "3", "4", "5"],
                        "search_text": "c-201 column 1 3 4 5",
                    },
                    {
                        "kind": "insert",
                        "source_line_number": None,
                        "output_line_number": 3,
                        "source_line": "",
                        "output_line": "D-301, WALL, 2, 4, 5",
                        "candidate_member_ids": ["D-301"],
                        "candidate_section_ids": ["S07"],
                        "candidate_card_ids": ["D-301"],
                        "geometry_bridge_member_ids": ["D-301"],
                        "exact_member_id_match": True,
                        "row_index": 2,
                        "row_id": "mgt-diff-row-0002",
                        "search_tokens": ["d-301", "wall", "2", "4", "5"],
                        "search_text": "d-301 wall 2 4 5",
                    },
                ],
                "source_vs_output_diff_window_count": 3,
                "total_change_count": 36,
                "supported_change_count": 36,
                "supported_change_ratio": 1.0,
                "direct_patch_change_count": 25,
                "direct_patch_change_ratio": 25 / 36,
                "patched_supported_change_count": 25,
                "instruction_sidecar_change_count": 0,
                "instruction_sidecar_change_ratio": 0.0,
                "instruction_sidecar_zero_touch_verified_change_count": 11,
                "instruction_sidecar_zero_touch_verified_change_ratio": 11 / 36,
                "unsupported_change_count": 0,
                "unsupported_change_ratio": 0.0,
                "audit_review_queue_item_count": 0,
                "audit_review_queue_pending_count": 0,
                "diff_summary_line": "compact diff | supported=36/36 | direct_patch=25 | sidecar=0 | unsupported=0",
                "diff_rows": [
                    {
                        "label": "Direct patch",
                        "value": "25",
                        "note": "beam section down and transfer connection detailing",
                        "tone": "good",
                    },
                    {
                        "label": "Sidecar",
                        "value": "0",
                        "note": "no audit-only carryover",
                        "tone": "neutral",
                    },
                ],
                "special_member_supported_action_family_label": "transfer_beam_connection_detailing=10",
                "special_member_direct_patch_action_family_label": "transfer_beam_connection_detailing=5",
                "special_member_zero_touch_verified_action_family_label": "transfer_beam_connection_detailing=5",
            },
            "artifacts": {
                "source_mgt": str(source_mgt),
                "output_mgt": str(output_mgt),
                "loadcomb_preview_mgt": str(loadcomb_preview),
                "loadcomb_roundtrip_report_json": str(loadcomb_roundtrip_report),
                "source_output_mgt_diff_json": str(source_output_diff_json),
                "source_output_mgt_diff_preview_txt": str(source_output_diff_preview),
                "source_output_mgt_diff_window_json": str(source_output_diff_window_json),
                "source_output_mgt_diff_window_preview_txt": str(source_output_diff_window_preview),
            },
        },
    )
    _write_json(
        roundtrip_gate_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary_line": "MIDAS native roundtrip: PASS | receipts=35/35 | loadcomb=35/35 exact | taxonomy=exact:34,canonical:1,lossy:0,unsupported:0,manual:0 | pending_review=0",
            "summary": {
                "corpus_case_count": 77,
                "native_writeback_ready_count": 35,
                "public_native_writeback_ready_count": 9,
                "public_source_writeback_ready_count": 25,
                "public_archive_structural_preview_writeback_ready_count": 8,
                "pending_review_total": 0,
                "loadcomb_exact_case_count": 35,
                "taxonomy_case_counts": {
                    "preserved_exact": 34,
                    "canonical_rewrite": 1,
                },
            },
        },
    )
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "fixture_case",
                "case_title": "Fixture Case",
                "case_note": "baseline vs optimized overlay fixture",
                "status_label": "baseline + ai compare",
                "mgt_export_report_path": str(export_report),
                "midas_native_roundtrip_gate_report_path": str(roundtrip_gate_report),
                "expert_review_metadata": {
                    "project_name": "Fixture Tower Retrofit",
                    "project_number": "PRJ-24017",
                    "client_name": "Fixture Development",
                    "site_name": "Seoul Block A",
                    "authority_name": "Seoul Metropolitan Review Board",
                    "permit_label": "Building Permit Review",
                    "committee_label": "Structural Peer Committee",
                    "package_purpose_label": "Jurisdictional Structural Review Package",
                    "package_id": "PKG-EX-017",
                    "issue_date": "2026-04-10",
                    "revision_code": "REV-A",
                    "revision_status": "Issued for authority review",
                    "prepared_by": "AI Structural Optimization Review Tool",
                    "reviewed_by": "Authority reviewer to sign",
                    "discipline_label": "Structural Optimization Review",
                    "issue_phase_label": "Authority review issue",
                    "checklist_head_label": "Authority issue checklist",
                    "checklist_title": "Authority / permit issue checklist",
                    "signoff_head_label": "Authority disposition",
                    "signoff_title": "Authority / reviewer disposition block",
                    "reviewer_label": "Authority reviewer / office",
                    "disposition_label": "Authority disposition",
                    "comments_label": "Authority comments / conditions",
                    "signature_label": "Authority signature / date",
                },
            },
            "baseline_structure": {
                "total_element_count": 128,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 9,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#f90'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0af'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0a7'/></svg>",
                "member_locator_rows": [
                    {
                        "member_id": "B-101",
                        "member_type": "beam",
                        "story_band_label": "S05",
                        "zone_label": "perimeter",
                        "action_name_label": "beam section down",
                        "cost_delta": -12.5,
                        "constructability_delta": -0.15,
                        "selection_gate_label": "hard gate pass",
                        "before_after_snapshot_note": "section A -> B",
                    },
                    {
                        "member_id": "C-201",
                        "member_type": "column",
                        "story_band_label": "S02",
                        "zone_label": "core",
                        "action_name_label": "rebar down",
                        "cost_delta": -4.2,
                        "constructability_delta": -0.03,
                        "selection_gate_label": "hard gate pass",
                        "before_after_snapshot_note": "rebar 0.02 -> 0.015",
                    },
                    {
                        "member_id": "W-404",
                        "member_type": "wall",
                        "story_band_label": "S04",
                        "zone_label": "core",
                        "action_name_label": "wall thickness down",
                        "cost_delta": -2.1,
                        "constructability_delta": -0.01,
                    },
                ],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {
                        "member_id": "B-101",
                        "category": "beam",
                        "story_band_label": "S05",
                        "section_id": 7,
                        "section_name": "H-400x200",
                        "color": "#8aa4d6",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    },
                    {
                        "member_id": "C-201",
                        "category": "column",
                        "story_band_label": "S02",
                        "section_id": 9,
                        "section_name": "C-600x600",
                        "color": "#5d8c72",
                        "p0": [4.0, 2.0, 0.0],
                        "p1": [4.0, 2.0, 6.0],
                    },
                ],
                "after_segments": [
                    {
                        "member_id": "B-101",
                        "group_id": "S05:perimeter:beam",
                        "action_name": "beam_section_down",
                        "story_band_label": "S05",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "before_section": "H-400x200",
                        "after_section": "H-350x175",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.9,
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.016,
                        "cost_delta": -12.5,
                        "constructability_delta": -0.15,
                        "max_dcr_after": 0.91,
                        "selection_gate_label": "hard gate pass",
                        "ai_reason": "Reserve remains below unity after beam section reduction",
                        "optimization_meaning_label": "material saved while D/C stays acceptable",
                        "action_family_label": "section reduction",
                        "review_handoff_summary": "Reviewer should confirm B-101 section change and linked MIDAS diff row.",
                        "source_output_diff_focus": "B-101 source/output beam row",
                        "linked_diff_row_count": 1,
                        "before_after_snapshot_note": "section H-400x200 -> H-350x175",
                        "color": "#2463eb",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "label": "beam",
                        "changed_group_count": 3,
                        "cost_proxy_delta_sum": -18.5,
                        "constructability_delta_sum": -0.3,
                        "max_dcr_after_max": 0.91,
                    },
                    {
                        "label": "column",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -4.2,
                        "constructability_delta_sum": -0.05,
                        "max_dcr_after_max": 0.72,
                    },
                ],
                "story_band_rows": [
                    {
                        "story_band": "S05",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 2,
                        "cost_proxy_delta_sum": -12.2,
                        "constructability_delta_sum": -0.2,
                        "max_dcr_after_max": 0.91,
                    },
                    {
                        "story_band": "S04",
                        "zone_label": "core",
                        "member_type": "wall",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -8.4,
                        "constructability_delta_sum": -0.1,
                        "max_dcr_after_max": 0.88,
                    },
                    {
                        "story_band": "S02",
                        "zone_label": "interior",
                        "member_type": "slab",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -4.1,
                        "constructability_delta_sum": -0.05,
                        "max_dcr_after_max": 0.76,
                    }
                ],
                "zone_rows": [
                    {
                        "label": "perimeter",
                        "changed_group_count": 2,
                        "cost_proxy_delta_sum": -12.2,
                        "constructability_delta_sum": -0.2,
                        "max_dcr_after_max": 0.91,
                    }
                ],
            },
            "artifact_links": {
                "viewer_html": "structural_optimization_viewer.html",
                "committee_dashboard_html": "../committee_review/committee_review_dashboard.html",
                "analysis_gallery_onepage_html": "analysis_evidence_gallery_onepage.html",
                "project_registry_report": "../release/project_registry.json",
                "project_package_zip": "../release/project_package.zip",
                "project_registry_signature": "../release/signing/project_registry.signature.b64",
                "external_benchmark_batch_job_report_json": "../release/external_benchmark_kickoff/external_benchmark_batch_job_report.json",
            },
        },
    )

    summary = module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_expert_review_issue_metadata.json",
    )

    assert out_html.exists()
    assert out_summary.exists()
    expert_html = tmp_path / "optimized_drawing_expert_review.html"
    assert expert_html.exists()
    expert_metadata_json = tmp_path / "optimized_drawing_expert_review.metadata.json"
    assert expert_metadata_json.exists()
    html_text = out_html.read_text(encoding="utf-8")
    expert_text = expert_html.read_text(encoding="utf-8")
    expert_metadata_payload = json.loads(expert_metadata_json.read_text(encoding="utf-8"))
    assert "Optimized Drawing Review" in html_text
    assert "Fixture Case" in html_text
    assert "Connected Review Route" in html_text
    assert "route-selection-target" in html_text
    assert "route_member_id" in html_text
    assert "route_story_band" in html_text
    assert "route_diff_index" in html_text
    assert "route_diff_row_id" in html_text
    assert "External Expert Mode" in html_text
    assert "Core viewer" in html_text
    assert "Project registry" in html_text
    assert "Project package zip" in html_text
    assert "Batch job report" in html_text
    assert "MGT EXPORT VERIFIED" in html_text
    assert "Workspace Dock" in html_text
    assert "dock-panel" in html_text
    assert "dock-status-line" in html_text
    assert "Display tree" in html_text
    assert "Model Explorer" in html_text
    assert "Audit queue pending" in html_text
    assert "Unsupported changes" in html_text
    assert "External Expert Mode" in html_text
    assert "Sheet-style drawing package surface" in html_text
    assert "sheet-package-surface" in html_text
    assert "drawing-sheet" in html_text
    assert "drawing-sheet-mini-grid" in html_text
    assert "drawing-sheet-link" in html_text
    assert "Why this changed" in html_text
    assert "Validation evidence" in html_text
    assert "Drawing package index" in html_text
    assert "Internal verification surface" in html_text
    assert "Traceable native export" in html_text
    assert "External experts should start with the sheet package above and only use this panel for native export audit details." in html_text
    assert "Start with the package sheets above for external review. Use this lower-priority panel only when you need native export audit detail, roundtrip context, or the exact verification tabs." in html_text
    assert "MGT verification workspace tabs" in html_text
    assert "mgt-tab-strip" in html_text
    assert "data-mgt-tab='summary'" in html_text
    assert "data-mgt-tab='compare'" in html_text
    assert "data-mgt-tab='raw'" in html_text
    assert "data-mgt-tab='artifacts'" in html_text
    assert "data-mgt-tab-panel='summary'" in html_text
    assert "data-mgt-tab-panel='compare'" in html_text
    assert "data-mgt-tab-panel='raw'" in html_text
    assert "data-mgt-tab-panel='artifacts'" in html_text
    assert "Story mini-highlights" in html_text
    assert "story-mini-strip" in html_text
    assert "story-mini-chip" in html_text
    assert "story-mini-chip.is-active" in html_text
    assert "story-mini-chip-track" in html_text
    assert "story-mini-chip-emphasis" in html_text
    assert "story-slot-pill" in html_text
    assert "Elevation slot 1 / 3" in html_text
    assert "Elevation slot 2 / 3" in html_text
    assert "Elevation slot 3 / 3" in html_text
    assert "elevation slots are shown as compact chips" in html_text
    assert "Hover to preview this story band in 3D. Click to center-fit the 3D view and commit selection." in html_text
    assert "data-story-chip='true'" in html_text
    assert "data-story-band-key='s05'" in html_text
    assert "role='button'" in html_text
    assert "tabindex='0'" in html_text
    assert "viewerState.previewStoryBand = ''" in html_text
    assert "node.addEventListener('mouseenter', preview)" in html_text
    assert "node.addEventListener('mouseleave', () => setPreviewStoryBand('', { render: true }))" in html_text
    assert "node.addEventListener('focus', preview)" in html_text
    assert "node.addEventListener('blur', () => setPreviewStoryBand('', { render: true }))" in html_text
    assert "MGT EXPORT VERIFIED" in html_text
    assert "Optimized .mgt" in html_text
    assert "MGT export report" in html_text
    assert "Source .mgt" in html_text
    assert "Diff JSON" in html_text
    assert "Diff TXT" in html_text
    assert "Native roundtrip gate" in html_text
    assert "contract=PASS" in html_text
    assert "output_mgt_exists=true" in html_text
    assert "loadcomb_roundtrip=true" in html_text
    assert "support=native_authoring_supported_changeset" in html_text
    assert "Summary" in html_text
    assert "Compare" in html_text
    assert "Raw diff" in html_text
    assert "Artifacts" in html_text
    assert "Source vs Optimized" in html_text
    assert "mgt-compare-panel" in html_text
    assert "mgt-compare-summary" in html_text
    assert "mgt-compare-preview" in html_text
    assert "mgt-compare-list" in html_text
    assert "mgt-compare-row" in html_text
    assert "data-compare-row" in html_text
    assert "Compare window:" in html_text
    assert "Window JSON" in html_text
    assert "Window TXT" in html_text
    assert "data-candidate-member-ids='B-101'" in html_text
    assert "data-geometry-bridge-member-ids='B-101'" in html_text
    assert "data-exact-member-id-match='true'" in html_text
    assert "data-diff-key" in html_text
    assert "mgt-compare-split" in html_text
    assert "mgt-compare-side" in html_text
    assert "Diff Window JSON" in html_text
    assert "Diff Window TXT" in html_text
    assert "mgt-diff-row-index-map" in html_text
    assert "diffRowIndexesForMember" in html_text
    assert "mgt-compare-sheet" in html_text
    assert "Page diff" in html_text
    assert "mgt-compare-pager-dock" in html_text
    assert "mgt-compare-pager" in html_text
    assert "mgt-compare-nav" in html_text
    assert "mgt-compare-nav-button" in html_text
    assert "mgt-compare-page-tab" in html_text
    assert "First" in html_text
    assert "Prev" in html_text
    assert "Next" in html_text
    assert "Last" in html_text
    assert "Page 1" in html_text
    assert "Source page" in html_text
    assert "Optimized page" in html_text
    assert "mgt-compare-page-text-grid" in html_text
    assert "mgt-compare-page-text-code" in html_text
    assert "mgt-compare-page" in html_text
    assert "mgt-compare-page-row" in html_text
    assert "data-compare-page='0'" in html_text
    assert "data-compare-page-tab='0'" in html_text
    assert "data-compare-page-panel='0'" in html_text
    assert "mgt-compare-page-side" in html_text
    assert "mgt-compare-page-code" in html_text
    assert "data-diff-index='0'" in html_text
    assert "data-diff-row-id='mgt-diff-row-0000'" in html_text
    assert html_text.count("const compareRowNodes = [...document.querySelectorAll('[data-compare-row]')];") == 1
    assert html_text.count("const comparePageRowNodes = [...document.querySelectorAll('[data-compare-page-row]')];") == 1
    assert "mgt-raw-diff-search" in html_text
    assert "mgt-raw-diff-count" in html_text
    assert "mgt-raw-diff-toolbar" in html_text
    assert "placeholder='raw diff line, card id, section id, token으로 필터'" in html_text
    assert "type='search'" in html_text
    assert "data-member-id" in html_text
    assert "data-raw-diff-line" in html_text
    assert "updateRawDiffFilter" in html_text
    assert "extractSearchTokens" in html_text
    assert "focusRelatedRawDiffRows" in html_text
    assert "rawDiffNodeByIndex" in html_text
    assert "compareRowNodeByIndex" in html_text
    assert "comparePageRowNodeByIndex" in html_text
    assert "activateComparePage" in html_text
    assert "stepComparePage" in html_text
    assert "updateComparePagerNav" in html_text
    assert "comparePageTabButtons.forEach" in html_text
    assert "comparePageNavButtons.forEach" in html_text
    assert "setHoveredCompareMember" in html_text
    assert "viewerState.hoveredCompareMemberId" in html_text
    assert "row.addEventListener('mouseenter'" in html_text
    assert "rawDiffSearchInput.addEventListener('input'" in html_text
    assert "matchMode: 'all'" in html_text
    assert "exactCompareRows.length" in html_text
    assert "is-match" in html_text
    assert "is-dim" in html_text
    assert "is-focused" in html_text
    assert "View presets" in html_text
    assert "Workspace state" in html_text
    assert "layer-toolbar" in html_text
    assert "AI Optimization Overlay Mode" in html_text
    assert "role='group' aria-label='AI optimization overlay mode'" in html_text
    assert "data-overlay-mode='member_type'" in html_text
    assert "data-overlay-mode='dcr'" in html_text
    assert "data-overlay-mode='cost_delta'" in html_text
    assert "data-overlay-mode='constructability'" in html_text
    assert "const overlayModeButtons = [...document.querySelectorAll('[data-overlay-mode]')]" in html_text
    assert "const overlayModeLegend = document.getElementById('overlay-mode-legend')" in html_text
    assert "overlayMode: 'member_type'" in html_text
    assert "const OVERLAY_MODE_LEGENDS = {" in html_text
    assert "function colorForDcr(segment)" in html_text
    assert "function colorForCostDelta(segment)" in html_text
    assert "function colorForConstructability(segment)" in html_text
    assert "if (value === null || value === undefined || value === '') return null;" in html_text
    assert "function colorForMemberType(segment, lane)" in html_text
    assert "function updateOverlayLegend()" in html_text
    assert "function setOverlayMode(mode)" in html_text
    assert "lane === 'optimized' ? colorForDcr(segment) : MIDAS_COLORS.neutral" in html_text
    assert "lane === 'optimized' ? colorForCostDelta(segment) : MIDAS_COLORS.neutral" in html_text
    assert "lane === 'optimized' ? colorForConstructability(segment) : MIDAS_COLORS.neutral" in html_text
    assert "overlayModeButtons.forEach((button) =>" in html_text
    assert "updateOverlayLegend();" in html_text
    assert "No D/C data" in html_text
    assert "No cost data" in html_text
    assert "No constructability data" in html_text
    assert "supported=36/36" in html_text
    assert "exact=34 canonical=1" in html_text
    assert "Compact diff" in html_text
    assert "source_output_mgt: changed=6" in html_text
    assert "mgt-raw-diff-list" in html_text
    assert "source_output_mgt preview" in html_text
    assert "Receipt: source_output_mgt diff receipt: ok" in html_text
    assert "S:13156" in html_text
    assert "O:14500" in html_text
    assert "source_vs_output_mgt: changed=6" in html_text
    assert "compact diff | supported=36/36 | direct_patch=25 | sidecar=0 | unsupported=0" in html_text
    assert "beam section down and transfer connection detailing" in html_text
    assert "Representative Changed Members" in html_text
    assert "External Expert Mode" in expert_text
    assert "Sheet E-01" in expert_text
    assert "Executive Review Sheet" in expert_text
    assert "Drawing Review Sheets" in expert_text
    assert "Why Changed / Representative Callouts" in expert_text
    assert "Validation Receipt" in expert_text
    assert "This package is organized for external structural review." in expert_text
    assert "Technical workspace" in expert_text
    assert "Optimized .mgt" in expert_text
    assert "Fixture Case" in expert_text
    assert "S05 perimeter beam changes cover 2 revision groups" in expert_text
    assert "Print / Save PDF" in expert_text
    assert "@page {" in expert_text
    assert "size:A3 landscape" in expert_text
    assert "@media print" in expert_text
    assert "display:table-header-group;" in expert_text
    assert "page-break-inside:avoid;" in expert_text
    assert "Jurisdictional Structural Review Package" in expert_text
    assert "Fixture Tower Retrofit" in expert_text
    assert "PRJ-24017" in expert_text
    assert "Fixture Development" in expert_text
    assert "Seoul Block A" in expert_text
    assert "Seoul Metropolitan Review Board" in expert_text
    assert "PKG-EX-017" in expert_text
    assert "Revision Stamp" in expert_text
    assert "REV-A" in expert_text
    assert "Issued for authority review" in expert_text
    assert "sheet-revision-stamp" in expert_text
    assert "sheet-footer-titleblock" in expert_text
    assert "AI Structural Optimization Review" in expert_text
    assert "Authority issue checklist" in expert_text
    assert "Authority / permit issue checklist" in expert_text
    assert "Authority disposition" in expert_text
    assert "Authority / reviewer disposition block" in expert_text
    assert "Approved / Approved as noted / Revise and resubmit" in expert_text
    assert "Reviewed By" in expert_text
    assert "Authority reviewer / office" in expert_text
    assert "Authority comments / conditions" in expert_text
    assert "Authority signature / date" in expert_text
    assert "Building Permit Review" in expert_text
    assert "Structural Peer Committee" in expert_text
    assert "This issue is arranged for browser Print to PDF" in expert_text
    assert summary["output_expert_html"] == str(expert_html)
    assert summary["output_expert_metadata_json"] == str(expert_metadata_json)
    assert summary["expert_review_metadata_json_href"] == "optimized_drawing_expert_review.metadata.json"
    assert "3D Structural Workspace" in html_text
    assert "XYZ canvas" in html_text
    assert "Selection Inspector" in html_text
    assert "Review Evidence Card" in html_text
    assert "inspector-evidence-card" in html_text
    assert "inspector-evidence-reason" in html_text
    assert "inspector-evidence-action" in html_text
    assert "inspector-evidence-dcr" in html_text
    assert "inspector-evidence-cost" in html_text
    assert "inspector-evidence-constructability" in html_text
    assert "inspector-evidence-diff-count" in html_text
    assert "inspector-evidence-diff-focus" in html_text
    assert "inspector-evidence-handoff" in html_text
    assert "No evidence selected." in html_text
    assert "Selection handoff: No data." in html_text
    assert "function updateMemberEvidenceCard(memberId)" in html_text
    assert "function updateStoryEvidenceCard(storyBand)" in html_text
    assert "function updateGridEvidenceCard(bubble)" in html_text
    assert "Story aggregate evidence for ${label}" in html_text
    assert "axis intersection" in html_text
    assert "const hasExplicitDiffCount = meta.linkedDiffRowCount !== null && meta.linkedDiffRowCount !== undefined && meta.linkedDiffRowCount !== ''" in html_text
    assert "diffRowIndexesForMember(memberId)" in html_text
    assert "viewer-3d-tooltip" in html_text
    assert "Axis source" in html_text
    assert "Axis refs" in html_text
    assert "drawMemberHoverHalo" in html_text
    assert "drawStageGridBackdrop" in html_text
    assert "drawAxisEdgeRepeatLabels" in html_text
    assert "drawGridIntersectionBubbles" in html_text
    assert "drawGridBubble" in html_text
    assert "precision-canvas-wrap::before" in html_text
    assert "precision-canvas-wrap::after" in html_text
    assert "min-height:clamp(560px, 72vh, 720px)" in html_text
    assert "height:clamp(560px, 72vh, 720px)" in html_text
    assert "min-height:clamp(380px, 62vh, 560px)" in html_text
    assert "height:clamp(380px, 62vh, 560px)" in html_text
    assert ".hero {\n  display:grid;\n  grid-template-columns:1.25fr .95fr;\n  gap:20px;\n  align-items:stretch;\n  min-width:0;" in html_text
    assert ".hero > * {\n  min-width:0;\n  max-width:100%;" in html_text
    assert ".hero-side {\n  padding:24px;\n  color:var(--ink);\n  overflow:hidden;" in html_text
    assert ".mgt-console {\n  margin-top:16px;" in html_text
    assert "max-width:100%;\n  min-width:0;\n  overflow:hidden;" in html_text
    assert "touch-action:none" in html_text
    assert "canvasCssWidth" in html_text
    assert "pixelRatio" in html_text
    assert "touchPoints: new Map()" in html_text
    assert "pinchStartDistance" in html_text
    assert "lastTapEligible" in html_text
    assert "function scheduleRender3D()" in html_text
    assert "window.requestAnimationFrame(() => render3DNow())" in html_text
    assert "function render3DNow()" in html_text
    assert "function render3D() {\n  scheduleRender3D();" in html_text
    assert "function zoomAtCanvasPoint(canvasX, canvasY, zoomFactor)" in html_text
    assert "viewerState.panX = canvasX - originX - (canvasX - originX - viewerState.panX) * scaleRatio" in html_text
    assert "function updatePinchGesture()" in html_text
    assert "touchPoints.size >= 2" in html_text
    assert "const centroid = gestureCentroid(points)" in html_text
    assert "nearestProjectedEntry(localX, localY, event.pointerType)" in html_text
    assert "coarsePointerHitRadius" in html_text
    assert "if (!viewerState.lastTapEligible) return;" in html_text
    assert "Math.hypot(event.clientX - viewerState.pointerDownX, event.clientY - viewerState.pointerDownY)" in html_text
    assert "data-full-label='Pinch zoom / 2-finger pan'" in html_text
    assert "data-mobile-label='Pinch / pan'" in html_text
    assert "const dpr = Math.min(Math.max(Number(window.devicePixelRatio || 1), 1), 2);" in html_text
    assert "const cssWidth = Math.max(1, Math.floor(rect.width));" in html_text
    assert "context.setTransform(dpr, 0, 0, dpr, 0, 0);" in html_text
    assert "function viewportWidth()" in html_text
    assert "viewportWidth() / 2 + viewerState.panX" in html_text
    assert "viewer-stage-hud" in html_text
    assert "viewer-stage-chip is-live" in html_text
    assert "baseline / optimized overlay" in html_text
    assert "data-mobile-label='Live'" in html_text
    assert ".viewer-stage-chip::after" in html_text
    assert "content:attr(data-mobile-label)" in html_text
    assert "viewer-axis-compass" in html_text
    assert "viewer-axis-node is-x" in html_text
    assert "viewer-status-ribbon" in html_text
    assert "Click member to pin" in html_text
    assert "data-mobile-label='Buttons zoom'" in html_text
    assert "data-mobile-label='Tap pin'" in html_text
    assert ".viewer-status-ribbon span::after" in html_text
    assert "top:var(--viewer-stage-ribbon-top)" in html_text
    assert "bottom:var(--viewer-stage-compass-bottom)" in html_text
    assert "viewer-viewport-controls" in html_text
    assert "role='group' aria-label='3D viewport direct controls'" in html_text
    assert "data-viewport-control='zoom-in'" in html_text
    assert "data-viewport-control='zoom-out'" in html_text
    assert "data-viewport-control='fit-view'" in html_text
    assert "tabindex='0'" in html_text
    assert "aria-label='Interactive 3D structural workspace canvas. Use plus and minus to zoom, arrow keys or WASD to orbit, Shift plus arrow keys or WASD to pan, Escape to clear selection, and 0 or F to fit the view.'" in html_text
    assert "aria-label='Zoom in 3D view'" in html_text
    assert "aria-label='Zoom out 3D view'" in html_text
    assert "aria-label='Fit and reset 3D view'" in html_text
    assert "id='viewer-selection-live' class='sr-only' aria-live='polite' aria-atomic='true'" in html_text
    assert "selection-overlay is-empty" in html_text
    assert "data-selection-clear" in html_text
    assert "data-selection-share" in html_text
    assert "aria-label='Clear selected member or grid bubble'" in html_text
    assert "aria-label='Copy selected member, story, or grid deep link'" in html_text
    assert "Copy link" in html_text
    assert "min-width:42px" in html_text
    assert "const viewportControlButtons = [...document.querySelectorAll('[data-viewport-control]')]" in html_text
    assert "const selectionLiveRegion = document.getElementById('viewer-selection-live')" in html_text
    assert "const clearSelectionButton = document.querySelector('[data-selection-clear]')" in html_text
    assert "const shareSelectionButton = document.querySelector('[data-selection-share]')" in html_text
    assert "applyViewportControl(button.dataset.viewportControl || '')" in html_text
    assert "viewerState.scale = clamp(viewerState.scale * 1.16, 1.6, 30)" in html_text
    assert "viewerState.scale = clamp(viewerState.scale / 1.16, 1.6, 30)" in html_text
    assert "resetCamera(viewerState.viewPreset || 'iso')" in html_text
    assert "function handleCanvasKeyboard(event)" in html_text
    assert "canvas.addEventListener('keydown', handleCanvasKeyboard)" in html_text
    assert "if (event.key === 'Escape')" in html_text
    assert "if (event.key === '+' || event.key === '=')" in html_text
    assert "if (event.key === '-' || event.key === '_')" in html_text
    assert "if (event.key === '0' || event.key.toLowerCase() === 'f')" in html_text
    assert "const keyboardPanStep = event.shiftKey ? 32 : 0" in html_text
    assert "const keyboardOrbitStep = event.shiftKey ? 0 : 0.08" in html_text
    assert "function commitWorkspaceSelection(selection = {}, options = {})" in html_text
    assert "function applyWorkspaceStorySelection(storyBand, options = {})" in html_text
    assert "function clearRelatedRawDiffRows(reason = 'member-level diff not selected')" in html_text
    assert "function syncWorkspaceDiffFocus(state = workspaceSelectionState(), options = {})" in html_text
    assert "return clearRelatedRawDiffRows('member-level diff not selected')" in html_text
    assert html_text.count("syncWorkspaceDiffFocus(workspaceSelectionState(), options)") >= 4
    assert "const storyMatch = key.match(/^s0*(\\d+)$/)" in html_text
    assert "return storyMatch ? storyMatch[1].replace(/^0+(?=\\d)/, '') : key.replace(/^0+(?=\\d)/, '')" in html_text
    assert "commitWorkspaceSelection({ kind: 'member', id: memberId" in html_text
    assert "commitWorkspaceSelection({ kind: 'grid', id: bubble.id" in html_text
    assert "commitWorkspaceSelection({ kind: 'clear', source: 'canvas-empty' }, { centerFit: false })" in html_text
    assert "commitWorkspaceSelection({ kind: 'story', id: storyBand" in html_text
    assert "commitWorkspaceSelection({ kind: 'clear'" in html_text
    assert "commitWorkspaceSelection({ kind: 'member', id: memberId, source: 'url-restore' }, { centerFit: true, syncUrl: true })" in html_text
    assert "commitWorkspaceSelection({ kind: 'story', id: storyBand, source: 'url-restore' }, { centerFit: true, syncUrl: true })" in html_text
    assert "commitWorkspaceSelection({ kind: 'member', id: memberRows[0].dataset.memberId || '', source: 'default-row' }, { centerFit: true, syncDiff: false })" in html_text
    assert "clearWorkspaceSelection(options = {}) {\n  return commitWorkspaceSelection({ kind: 'clear', source: options.source || 'clear' }, options);" in html_text
    assert "function stableGridBubbleId(xLabel, yLabel)" in html_text
    assert "const bubbleId = stableGridBubbleId(xLabel, yLabel)" in html_text
    assert "function storyBandSelectionCounts(storyBand)" in html_text
    assert "renderable rows=" in html_text
    assert "invalid rows excluded=" in html_text
    assert "geometry=valid rows" in html_text
    assert "Renderable story segments: ${counts.renderable} of ${counts.total} total" in html_text
    assert "invalid rows excluded" in html_text
    assert "Canonical selection deep link keeps ${label} reviewer handoff." in html_text
    assert "renderable segments out of ${counts.total} total" in html_text
    assert "function updateStorySelectionOverlay(storyBand)" in html_text
    assert "Story ${label} selected" in html_text
    assert "row.setAttribute('aria-selected', String(active))" in html_text
    assert "--viewer-stage-ribbon-top:56px" in html_text
    assert "--viewer-stage-overlay-bottom:12px" in html_text
    assert "function clearWorkspaceSelection(options = {})" in html_text
    assert "function restoreWorkspaceSelectionFromUrl()" in html_text
    assert "return true;" in html_text
    assert "function syncWorkspaceUrlState(options = {})" in html_text
    assert "function buildWorkspaceDeepLink()" in html_text
    assert module.WORKSPACE_SELECTION_CONTRACT_VERSION == "optimized-review-workspace-selection-v1"
    assert module.WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION == "optimized-review-workspace-diff-focus-v1"
    assert f'const WORKSPACE_SELECTION_CONTRACT_VERSION = "{module.WORKSPACE_SELECTION_CONTRACT_VERSION}";' in html_text
    assert f'const WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION = "{module.WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION}";' in html_text
    assert "function workspaceSelectionState()" in html_text
    assert "function writeWorkspaceSelectionParams(params, state)" in html_text
    assert "const CANONICAL_WORKSPACE_SELECTION_PARAMS = [" in html_text
    assert "'selection_kind'" in html_text
    assert "'selection_id'" in html_text
    assert "'selection_label'" in html_text
    assert "'selection_provenance'" in html_text
    assert "'selection_story'" in html_text
    assert "'selection_contract_version'" in html_text
    assert "function deleteWorkspaceSelectionParams(params)" in html_text
    assert "provenance: 'member-table'" in html_text
    assert "provenance: 'story-band'" in html_text
    assert "provenance: 'grid-bubble'" in html_text
    assert "provenance: 'hash-cleanup'" in html_text
    selection_delete_helper = html_text[
        html_text.index("function deleteWorkspaceSelectionParams(params)") :
        html_text.index("function hasCanonicalWorkspaceSelectionParams(params)")
    ]
    selection_writer = html_text[
        html_text.index("function writeWorkspaceSelectionParams(params, state)") :
        html_text.index("function syncWorkspaceUrlState(options = {})")
    ]
    assert "LEGACY_WORKSPACE_SELECTION_PARAMS.forEach((key) => params.delete(key));" in selection_delete_helper
    assert "CANONICAL_WORKSPACE_SELECTION_PARAMS.forEach((key) => params.delete(key));" in selection_delete_helper
    assert "deleteWorkspaceSelectionParams(params);" in selection_writer
    assert "params.set('selection_kind', state.kind)" in selection_writer
    assert "params.set('selection_id', state.id)" in selection_writer
    assert "params.set('selection_contract_version', WORKSPACE_SELECTION_CONTRACT_VERSION)" in selection_writer
    assert "params.set('selection_label', state.label)" in selection_writer
    assert "params.set('selection_provenance', state.provenance)" in selection_writer
    assert "params.set('selection_story', state.story)" in selection_writer
    assert "params.set('member', state.id)" not in selection_writer
    assert "params.set('story', state.story)" not in selection_writer
    assert "params.set('grid', state.id)" not in selection_writer
    build_deep_link = html_text[
        html_text.index("function buildWorkspaceDeepLink()") :
        html_text.index("function copyTextWithFallback(text)")
    ]
    sync_url_state = html_text[
        html_text.index("function syncWorkspaceUrlState(options = {})") :
        html_text.index("function buildWorkspaceDeepLink()")
    ]
    assert "writeWorkspaceSelectionParams(params, state)" in build_deep_link
    assert "writeWorkspaceSelectionParams(params, workspaceSelectionState())" in sync_url_state
    assert "cleanupWorkspaceSelectionHashParams(url)" in build_deep_link
    assert "cleanupWorkspaceSelectionHashParams(url)" in sync_url_state
    assert "hasCanonicalWorkspaceSelectionParams(searchParams)" in html_text
    assert "selectionKind: searchParams.get('selection_kind') || hashParams.get('selection_kind') || ''" in html_text
    assert "selectionId: searchParams.get('selection_id') || hashParams.get('selection_id') || ''" in html_text
    assert "selectionLabel: searchParams.get('selection_label') || hashParams.get('selection_label') || ''" in html_text
    assert "selectionProvenance: searchParams.get('selection_provenance') || hashParams.get('selection_provenance') || ''" in html_text
    assert "selectionStory: searchParams.get('selection_story') || hashParams.get('selection_story') || ''" in html_text
    assert "selectionContractVersion: searchParams.get('selection_contract_version') || hashParams.get('selection_contract_version') || ''" in html_text
    assert "const canonicalKind = String(params.selectionKind || '').trim().toLowerCase();" in html_text
    assert "const canonicalId = String(params.selectionId || '').trim();" in html_text
    assert "if (canonicalKind === 'clear')" in html_text
    assert "source: 'url-restore-invalid-canonical'" in html_text
    assert "if (canonicalKind && canonicalId) {" in html_text
    assert "if (canonicalKind === 'member' && memberRows.some((row) => row.dataset.memberId === canonicalId))" in html_text
    assert "commitWorkspaceSelection({ kind: 'member', id: canonicalId, source: 'url-restore' }, { centerFit: true, syncUrl: true })" in html_text
    assert "commitWorkspaceSelection({ kind: 'story', id: canonicalId, source: 'url-restore' }, { centerFit: true, syncUrl: true })" in html_text
    assert "commitWorkspaceSelection({ kind: 'grid', id: canonicalId, source: 'url-restore' }, { centerFit: false, syncUrl: true })" in html_text
    assert "Restore priority: member > story > grid" in html_text
    assert "function copyTextWithFallback(text)" in html_text
    assert "function copyWorkspaceDeepLink()" in html_text
    assert "navigator.clipboard.writeText(text)" in html_text
    assert "document.execCommand('copy')" in html_text
    assert "announceSelection('No selected member, story, or grid to copy')" in html_text
    assert "announceSelection('Selection deep link copied')" in html_text
    assert "announceSelection('Could not copy selection deep link. Select and copy the browser URL manually.')" in html_text
    assert "grid: searchParams.get('grid') || hashParams.get('grid') || ''" in html_text
    assert "const gridBubbleId = String(params.grid || '').trim();" in html_text
    assert "if (!viewerState.gridBubbles.length) {\n      render3DNow();" in html_text
    assert "commitWorkspaceSelection({ kind: 'grid', id: gridBubbleId, source: 'url-restore' }, { centerFit: false, syncUrl: true })" in html_text
    assert "const restoredWorkspaceSelection = restoreWorkspaceSelectionFromUrl();" in html_text
    assert "if (memberRows.length && !restoredWorkspaceSelection)" in html_text
    assert "aria-selected='false'" in html_text
    assert "row.setAttribute('aria-selected', String(selected))" in html_text
    assert "row.addEventListener('keydown', (event) =>" in html_text
    assert "tbody tr:focus-visible" in html_text
    assert "clearSelectionButton.addEventListener('click'" in html_text
    assert "shareSelectionButton.addEventListener('click'" in html_text
    assert ".selection-overlay {" in html_text
    assert ".selection-overlay.is-empty" in html_text
    assert ".selection-clear-button" in html_text
    assert ".selection-share-button" in html_text
    assert "body:has(.selection-overlay) .precision-canvas-wrap" not in html_text
    assert "bottom:var(--viewer-stage-overlay-bottom)" in html_text
    assert "border-radius:18px 18px 14px 14px" in html_text
    assert "max-height:28%" in html_text
    assert ".viewer-3d-grid > .precision-pane" in html_text
    assert "data-3d-toggle='beam'" in html_text
    assert "data-camera-flip-180" in html_text
    assert "Flip 180" in html_text
    assert "viewerState.flipAxisSign *= -1" in html_text
    assert "const flippedDx = viewerState.flipAxisSign === -1 ? -dx : dx" in html_text
    assert "const flippedDz = viewerState.flipAxisSign === -1 ? -dz : dz" in html_text
    assert "viewerState.activeStoryBand" in html_text
    assert "viewerState.previewStoryBand" in html_text
    assert "normalizeStoryBandKey" in html_text
    assert "storyBandSegmentsFor" in html_text
    assert "setActiveStoryBand" in html_text
    assert "setPreviewStoryBand" in html_text
    assert "focusStoryBand" in html_text
    assert "drawStoryBandHalo" in html_text
    assert "drawStoryBandHalo(entry, { preview: true })" in html_text
    assert "storyBandRows.forEach" in html_text
    assert "storyChipNodes.forEach" in html_text
    assert "data-story-band-row='true'" in html_text
    assert "node.addEventListener('mouseenter'" in html_text
    assert "node.addEventListener('focus'" in html_text
    assert "node.addEventListener('mouseleave'" in html_text
    assert "node.addEventListener('blur'" in html_text
    assert "row.addEventListener('keydown'" in html_text
    assert "tbody tr.story-band-row" in html_text
    assert "tbody tr.is-story-active" in html_text
    assert "class='table-wrap story-table-wrap'" in html_text
    assert "data-label='Elevation slot'" in html_text
    assert ".story-table-wrap table" in html_text
    assert "class='table-wrap member-table-wrap'" in html_text
    assert "data-label='Member'" in html_text
    assert ".member-table-wrap table" in html_text
    assert ".member-table-wrap tbody tr" in html_text
    assert "grid-template-columns:104px minmax(0, 1fr)" in html_text
    assert ".table-wrap {\n    overflow-x:hidden;\n    width:100%;\n    max-width:100%;\n    min-width:0;" in html_text
    assert ".table-wrap table {\n    min-width:0;\n    table-layout:fixed;" in html_text
    assert ".mgt-verification-grid,\n  .mgt-console-grid,\n  .mgt-diff-grid,\n  .mgt-raw-diff-metrics,\n  .mgt-raw-diff-toolbar,\n  .mgt-compare-pager-dock,\n  .mgt-compare-page-text-grid,\n  .mgt-compare-page-row,\n  .mgt-compare-page-split,\n  .mgt-compare-split {\n    grid-template-columns:1fr;" in html_text
    assert "Open</a>" in html_text
    assert "viewer-3d-canvas" in html_text
    assert "optimized-review-3d-data" in html_text
    assert "function isRenderableSegment(segment)" in html_text
    assert "function coordinateStatusText(row)" in html_text
    assert "function coordinateFallbackReasonText(row)" in html_text
    assert "coordinate_fallback_diagnostics" in html_text
    assert "coordinate_fallback_provenance" in html_text
    assert "if (!isRenderableSegment(segment)) return;" in html_text
    assert "const focusMatches = counts.renderableMatches;" in html_text
    assert "coordinates unavailable" in html_text
    assert "toggleCameraFlip180" in html_text
    assert "cameraFlipButton.addEventListener('click'" in html_text

    payload = json.loads(out_summary.read_text(encoding="utf-8"))
    assert payload["changed_group_count"] == 4
    assert payload["changed_member_count"] == 9
    assert payload["projection_count"] == 3
    assert payload["top_member_count"] == 3
    assert payload["precision_mode"] == "interactive_canvas_xyz_structure"
    assert payload["interactive_3d_payload"]["axis_ref_source_mode"] == "geometry_derived_axis_refs"
    assert payload["interactive_3d_payload"]["after_segments"][0]["cost_delta"] == -12.5
    assert payload["interactive_3d_payload"]["after_segments"][0]["constructability_delta"] == -0.15
    assert payload["interactive_3d_payload"]["after_segments"][0]["max_dcr_after"] == 0.91
    assert payload["interactive_3d_payload"]["after_segments"][0]["ai_reason"] == "Reserve remains below unity after beam section reduction"
    assert payload["interactive_3d_payload"]["after_segments"][0]["optimization_meaning_label"] == "material saved while D/C stays acceptable"
    assert payload["interactive_3d_payload"]["after_segments"][0]["action_family_label"] == "section reduction"
    assert payload["interactive_3d_payload"]["after_segments"][0]["selection_gate_label"] == "hard gate pass"
    assert payload["interactive_3d_payload"]["after_segments"][0]["review_handoff_summary"] == "Reviewer should confirm B-101 section change and linked MIDAS diff row."
    assert payload["interactive_3d_payload"]["after_segments"][0]["source_output_diff_focus"] == "B-101 source/output beam row"
    assert payload["interactive_3d_payload"]["after_segments"][0]["linked_diff_row_count"] == 1.0
    assert payload["interactive_3d_payload_contract_version"] == payload["interactive_3d_payload"]["interactive_3d_payload_contract_version"]
    assert payload["interactive_3d_nullable_metric_fields"] == [
        "cost_delta",
        "constructability_delta",
        "max_dcr_after",
        "linked_diff_row_count",
    ]
    assert "ai_reason" in payload["interactive_3d_evidence_field_names"]
    assert payload["interactive_3d_after_segment_contract_validation"]["after_segment_count_matches"] is True
    assert payload["interactive_3d_after_segment_contract_validation"]["compact_after_segment_count"] == payload["interactive_3d_payload"]["after_segment_count"]
    assert payload["interactive_3d_coordinate_contract_version"] == payload["interactive_3d_payload"]["coordinate_contract_version"]
    assert "invalid_coordinate_count" in payload["interactive_3d_coordinate_contract_validation"]
    assert payload["interactive_3d_workspace_selection_contract_version"] == module.WORKSPACE_SELECTION_CONTRACT_VERSION
    assert payload["interactive_3d_workspace_diff_focus_contract_version"] == module.WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION
    assert payload["interactive_3d_payload"]["workspace_selection_contract_version"] == module.WORKSPACE_SELECTION_CONTRACT_VERSION
    assert payload["interactive_3d_payload"]["workspace_diff_focus_contract_version"] == module.WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION
    assert payload["interactive_3d_workspace_selection_contract_features"] == {
        "member_restore": True,
        "story_restore": True,
        "grid_restore": True,
        "stale_param_cleanup": True,
        "member_diff_focus": True,
        "non_member_diff_clear": True,
    }
    assert payload["interactive_3d_payload"]["workspace_selection_contract_features"] == payload["interactive_3d_workspace_selection_contract_features"]
    handoff_contracts = payload["export_handoff_contracts"]
    assert handoff_contracts["workspace_selection_contract"] == {
        "selection_contract_version": module.WORKSPACE_SELECTION_CONTRACT_VERSION,
        "feature_flags": payload["interactive_3d_workspace_selection_contract_features"],
        "canonical_param_names": [
            "selection_kind",
            "selection_id",
            "selection_label",
            "selection_provenance",
            "selection_story",
            "selection_contract_version",
        ],
    }
    assert handoff_contracts["workspace_diff_focus_contract"] == {
        "diff_focus_contract_version": module.WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION,
        "member_scoped_focus": True,
        "non_member_clear_semantics": True,
        "member_row_indices_available": True,
    }
    assert handoff_contracts["raw_diff_artifact_contract"] == {
        "source_output_diff_json_href": "midas_generator_33.optimized.source_output_diff.json",
        "source_output_diff_txt_href": "midas_generator_33.optimized.source_output_diff.txt",
        "source_output_diff_window_json_href": "midas_generator_33.optimized.source_output_diff_window.json",
        "source_output_diff_window_txt_href": "midas_generator_33.optimized.source_output_diff_window.txt",
        "source_output_diff_json_available": True,
        "source_output_diff_txt_available": True,
        "source_output_diff_window_json_available": True,
        "source_output_diff_window_txt_available": True,
        "changed_line_count": 6,
        "added_line_count": 2,
        "removed_line_count": 0,
        "total_delta_count": 8,
        "member_row_indices_available": True,
        "member_row_indices": {"B-101": [0], "C-201": [1], "D-301": [2]},
        "window_member_row_indices_available": True,
        "window_member_row_indices": {"B-101": [0], "C-201": [1], "D-301": [2]},
    }
    archive_contract = handoff_contracts["archive_handoff_contract"]
    assert archive_contract["contract_version"] == "optimized-review-archive-handoff-v1"
    assert archive_contract["pass"] is True
    assert archive_contract["hrefs"] == {
        "optimized_review_html_href": "optimized_drawing_review.html",
        "expert_review_html_href": "optimized_drawing_expert_review.html",
        "review_summary_json_href": "optimized_drawing_review_summary.json",
        "expert_metadata_json_href": "optimized_drawing_expert_review.metadata.json",
        "project_registry_href": "../release/project_registry.json",
        "project_package_zip_href": "../release/project_package.zip",
        "project_registry_signature_href": "../release/signing/project_registry.signature.b64",
        "mgt_export_report_href": "midas_generator_33.optimized.export_report.json",
        "mgt_source_mgt_href": "midas_generator_33.mgt",
        "mgt_optimized_mgt_href": "midas_generator_33.optimized.mgt",
        "mgt_loadcomb_roundtrip_report_href": "midas_generator_33.optimized.loadcomb_roundtrip_report.json",
        "midas_roundtrip_gate_report_href": "midas_native_roundtrip_gate_report.json",
    }
    assert archive_contract["artifact_href_validation_summary"]["pass"] is True
    assert archive_contract["artifact_href_validation_summary"]["missing_required_count"] == 0
    assert archive_contract["artifact_href_validation_summary"]["missing_optional_count"] == 3
    assert archive_contract["artifact_href_validation_summary"]["missing_optional_keys"] == [
        "project_package_zip_href",
        "project_registry_href",
        "project_registry_signature_href",
    ]
    assert payload["artifact_href_validation"]["pass"] is True
    assert payload["artifact_href_validation"]["missing_required_count"] == 0
    assert "mgt_output_mgt_href" not in payload["artifact_href_validation"]["missing_required_keys"]
    missing_metric_segment = module._compact_3d_after_segment({"member_id": "NO-METRIC", "p0": [0, 0, 0], "p1": [1, 1, 1]})
    assert missing_metric_segment["cost_delta"] is None
    assert missing_metric_segment["constructability_delta"] is None
    assert missing_metric_segment["max_dcr_after"] is None
    assert missing_metric_segment["linked_diff_row_count"] is None
    assert missing_metric_segment["review_handoff_summary"] == ""
    assert payload["mgt_export_contract_pass"] is True
    assert payload["mgt_export_output_mgt_exists"] is True
    assert payload["mgt_export_loadcomb_roundtrip_pass"] is True
    assert payload["mgt_export_loadcomb_combo_count"] == 8
    assert payload["mgt_export_audit_review_queue_pending_count"] == 0
    assert payload["mgt_export_unsupported_change_count"] == 0
    assert payload["mgt_export_support_mode"] == "native_authoring_supported_changeset"
    assert payload["mgt_export_total_change_count"] == 36
    assert payload["mgt_export_instruction_sidecar_zero_touch_verified_change_count"] == 11
    assert payload["mgt_source_mgt_href"] == "midas_generator_33.mgt"
    assert payload["mgt_export_source_output_mgt_diff_available"] is True
    assert payload["mgt_export_source_output_mgt_summary_line"].startswith("source_output_mgt: changed=6")
    assert payload["mgt_export_source_output_mgt_source_meaningful_line_count"] == 37250
    assert payload["mgt_export_source_output_mgt_output_meaningful_line_count"] == 37281
    assert payload["mgt_export_source_output_mgt_changed_line_count"] == 6
    assert payload["mgt_export_source_output_mgt_total_delta_count"] == 8
    assert payload["mgt_export_source_output_mgt_diff_json_exists"] is True
    assert payload["mgt_export_source_output_mgt_diff_preview_exists"] is True
    assert payload["mgt_export_source_output_mgt_diff_window_json_exists"] is True
    assert payload["mgt_export_source_output_mgt_diff_window_preview_exists"] is True
    assert payload["mgt_export_source_output_mgt_verification_receipt_line"].startswith("source_output_mgt diff receipt: ok")
    assert "source_output_mgt preview" in payload["mgt_export_source_output_mgt_diff_preview_text"]
    assert "MIDAS source vs output diff window" in payload["mgt_export_source_output_mgt_diff_window_preview_text"]
    assert len(payload["mgt_export_source_output_mgt_diff_sample_lines"]) == 2
    assert payload["mgt_export_source_output_mgt_diff_window_member_ids"] == ["B-101", "C-201", "D-301"]
    assert payload["mgt_export_source_output_mgt_diff_window_member_row_indices"] == {"B-101": [0], "C-201": [1], "D-301": [2]}
    assert payload["mgt_compare_window_available"] is True
    assert payload["mgt_compare_window_row_count"] == 3
    assert payload["mgt_compare_window_summary_line"].startswith("source_output_mgt window: changed=6")
    assert payload["mgt_compare_window_json_href"] == "midas_generator_33.optimized.source_output_diff_window.json"
    assert payload["mgt_compare_window_txt_href"] == "midas_generator_33.optimized.source_output_diff_window.txt"
    assert "window_count=3" in payload["mgt_compare_window_preview_text"]
    assert payload["mgt_compare_window_member_row_indices"] == {"B-101": [0], "C-201": [1], "D-301": [2]}
    assert payload["mgt_export_source_vs_output_diff_changed_line_count"] == 6
    assert payload["mgt_export_source_vs_output_diff_sample_count"] == 2
    assert payload["mgt_export_source_vs_output_diff_window_count"] == 3
    assert payload["mgt_source_output_diff_json_href"] == "midas_generator_33.optimized.source_output_diff.json"
    assert payload["mgt_source_output_diff_preview_href"] == "midas_generator_33.optimized.source_output_diff.txt"
    assert payload["mgt_source_output_diff_window_json_href"] == "midas_generator_33.optimized.source_output_diff_window.json"
    assert payload["mgt_source_output_diff_window_preview_href"] == "midas_generator_33.optimized.source_output_diff_window.txt"
    assert payload["midas_roundtrip_gate_corpus_case_count"] == 77
    assert payload["midas_roundtrip_gate_public_source_ready_count"] == 25
    assert payload["midas_roundtrip_gate_public_structural_preview_ready_count"] == 8
    assert payload["midas_roundtrip_gate_taxonomy_exact_count"] == 34
    assert payload["midas_roundtrip_gate_taxonomy_canonical_count"] == 1
    assert payload["story_band_priority_count"] == 3
    assert payload["story_schedule_rows"][0]["story_band"] == "S05"
    assert payload["story_schedule_rows"][0]["total_segment_count"] == 2
    assert payload["story_schedule_rows"][0]["renderable_segment_count"] == 2
    assert payload["story_schedule_rows"][0]["focusable_segment_count"] == 2
    assert payload["story_schedule_rows"][0]["invalid_excluded_count"] == 0
    assert payload["mgt_export_diff_summary_line"] == "compact diff | supported=36/36 | direct_patch=25 | sidecar=0 | unsupported=0"
    assert payload["mgt_export_diff_rows"][0]["label"] == "Direct patch"
    assert payload["output_expert_metadata_json"] == str(expert_metadata_json)
    assert payload["expert_review_metadata_json_href"] == "optimized_drawing_expert_review.metadata.json"

    assert expert_metadata_payload["schema_version"] == "optimized_drawing_expert_review.metadata.v1"
    assert expert_metadata_payload["issue_metadata_source_mode"] == "template_metadata_json+viewer_case_context_metadata"
    assert expert_metadata_payload["issue_fields"]["project_name"] == "Fixture Tower Retrofit"
    assert expert_metadata_payload["issue_fields"]["project_number"] == "PRJ-24017"
    assert expert_metadata_payload["issue_fields"]["issue_id"] == "PKG-EX-017"
    assert expert_metadata_payload["issue_fields"]["revision_code"] == "REV-A"
    assert expert_metadata_payload["issue_fields"]["authority_name"] == "Seoul Metropolitan Review Board"
    assert expert_metadata_payload["artifacts"]["hrefs"]["optimized_review_html"] == "optimized_drawing_review.html"
    assert expert_metadata_payload["artifacts"]["hrefs"]["expert_review_html"] == "optimized_drawing_expert_review.html"
    assert expert_metadata_payload["artifacts"]["hrefs"]["project_registry_report"] == "../release/project_registry.json"
    assert expert_metadata_payload["artifacts"]["hrefs"]["project_package_zip"] == "../release/project_package.zip"
    assert expert_metadata_payload["artifacts"]["hrefs"]["mgt_source_output_diff_json"] == "midas_generator_33.optimized.source_output_diff.json"
    assert expert_metadata_payload["artifacts"]["hrefs"]["mgt_source_output_diff_txt"] == "midas_generator_33.optimized.source_output_diff.txt"
    assert expert_metadata_payload["artifacts"]["hrefs"]["mgt_source_output_diff_window_json"] == "midas_generator_33.optimized.source_output_diff_window.json"
    assert expert_metadata_payload["artifacts"]["hrefs"]["mgt_source_output_diff_window_txt"] == "midas_generator_33.optimized.source_output_diff_window.txt"
    assert (
        expert_metadata_payload["artifacts"]["hrefs"]["external_benchmark_batch_job_report_json"]
        == "../release/external_benchmark_kickoff/external_benchmark_batch_job_report.json"
    )
    assert expert_metadata_payload["summary"]["precision_mode"] == "interactive_canvas_xyz_structure"
    assert expert_metadata_payload["summary"]["axis_ref_source_mode"] == "geometry_derived_axis_refs"
    assert expert_metadata_payload["export_handoff_contracts"] == handoff_contracts
    assert expert_metadata_payload["artifact_href_validation"]["pass"] is True
    assert expert_metadata_payload["artifacts"]["href_validation"]["missing_required_count"] == 0
    story_schedule_rows = expert_metadata_payload["story_schedule_rows"]
    assert story_schedule_rows[0]["story_band"] == "S05"
    assert story_schedule_rows[0]["total_segment_count"] == 2
    assert story_schedule_rows[0]["renderable_segment_count"] == 2
    assert story_schedule_rows[0]["focusable_segment_count"] == 2
    assert story_schedule_rows[0]["invalid_excluded_count"] == 0
    assert story_schedule_rows[1]["story_band"] == "S04"
    assert story_schedule_rows[1]["total_segment_count"] == 0
    assert story_schedule_rows[1]["renderable_segment_count"] == 0
    assert story_schedule_rows[1]["focusable_segment_count"] == 0
    assert story_schedule_rows[1]["invalid_excluded_count"] == 0
    assert story_schedule_rows[2]["story_band"] == "S02"
    assert story_schedule_rows[2]["total_segment_count"] == 1
    assert story_schedule_rows[2]["renderable_segment_count"] == 1
    assert story_schedule_rows[2]["focusable_segment_count"] == 1
    assert story_schedule_rows[2]["invalid_excluded_count"] == 0
    representative_member = expert_metadata_payload["representative_members"][0]
    assert representative_member["member_id"] == "B-101"
    selection_query = parse_qs(urlsplit(representative_member["selection_deep_link_href"]).query)
    assert selection_query["selection_kind"] == ["member"]
    assert selection_query["selection_id"] == ["B-101"]
    assert selection_query["selection_label"] == ["B-101"]
    assert selection_query["selection_provenance"] == ["member-table"]
    assert selection_query["selection_story"] == ["S05"]
    assert selection_query["selection_contract_version"] == [module.WORKSPACE_SELECTION_CONTRACT_VERSION]
    legacy_query = parse_qs(urlsplit(representative_member["viewer_focus_href"]).query)
    assert legacy_query["focus_member"] == ["B-101"]
    assert legacy_query["member_id"] == ["B-101"]
    assert legacy_query["case_id"] == ["B-101"]
    assert representative_member["selection_gate_label"] == "hard gate pass"
    assert representative_member["ai_reason"] == "Reserve remains below unity after beam section reduction"
    assert representative_member["review_handoff_summary"] == "Reviewer should confirm B-101 section change and linked MIDAS diff row."
    assert representative_member["source_output_diff_focus"] == "B-101 source/output beam row"
    assert representative_member["linked_diff_row_count"] == 1.0
    assert representative_member["evidence_completeness_status"] == "complete"
    assert representative_member["missing_evidence_fields"] == []
    missing_evidence_member = next(
        row for row in expert_metadata_payload["representative_members"] if row["member_id"] == "W-404"
    )
    assert missing_evidence_member["evidence_completeness_status"] == "missing"
    assert missing_evidence_member["missing_evidence_fields"] == [
        "ai_reason",
        "review_handoff_summary",
        "source_output_diff_focus",
        "linked_diff_row_count",
    ]
    assert missing_evidence_member["missing_evidence_labels"]["ai_reason"] == "No data"
    assert missing_evidence_member["missing_evidence_labels"]["review_handoff_summary"] == "No data"
    assert missing_evidence_member["missing_evidence_labels"]["source_output_diff_focus"] == "No data"
    assert missing_evidence_member["missing_evidence_labels"]["linked_diff_row_count"] == "not linked"
    assert expert_metadata_payload["representative_evidence_completeness_summary"] == {
        "total": 3,
        "complete": 1,
        "partial": 0,
        "missing": 2,
        "missing_evidence_field_counts": {
            "ai_reason": 2,
            "review_handoff_summary": 2,
            "source_output_diff_focus": 2,
            "linked_diff_row_count": 2,
        },
    }
    assert expert_metadata_payload["validation_rows"][0]["label"] == "MIDAS native export"
    assert expert_metadata_payload["reviewer_checklist_items"][0]["checked"] is True
    assert "Project registry" in expert_text
    assert "Project package zip" in expert_text
    assert "Batch job report" in expert_text
    assert "Representative Evidence Receipt" in expert_text
    assert "expert-evidence-receipt" in expert_text
    assert "missing_evidence_fields" in expert_text
    assert "linked_diff_row_count" in expert_text
    assert "No data" in expert_text
    assert "not linked" in expert_text
    assert "is-complete" in expert_text
    assert "is-missing" in expert_text
    assert "B-101" in expert_text
    assert "W-404" in expert_text

    assets_dir = out_html.parent / "optimized_drawing_review_assets"
    assert (assets_dir / "optimized_drawing_review.plan_xy.baseline.svg").exists()
    assert (assets_dir / "optimized_drawing_review.plan_xy.overlay.svg").exists()
    assert summary["output_assets_dir"] == str(assets_dir)


def test_write_review_artifacts_prefers_upstream_named_axis_refs(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    upstream_model = tmp_path / "model.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"

    _write_json(
        upstream_model,
        {
            "model": {
                "metadata": {
                    "named_axis_refs": {
                        "x": [{"label": "A", "value": 0.0}, {"label": "B", "value": 8.0}],
                        "y": [{"label": "1", "value": 0.0}, {"label": "2", "value": 6.0}],
                        "z": [{"label": "L1", "value": 0.0}, {"label": "L2", "value": 3.6}],
                    }
                }
            }
        },
    )
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "fixture_case_named_axis",
                "case_title": "Fixture Case Named Axis",
                "case_note": "viewer should prefer upstream named axis refs",
                "status_label": "baseline + ai compare",
                "model_path": str(upstream_model),
            },
            "baseline_structure": {
                "total_element_count": 2,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#f90'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0af'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0a7'/></svg>",
                "member_locator_rows": [
                    {
                        "member_id": "B-101",
                        "member_type": "beam",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "action_name_label": "beam section down",
                        "cost_delta": -12.5,
                        "constructability_delta": -0.15,
                        "selection_gate_label": "hard gate pass",
                        "before_after_snapshot_note": "section A -> B",
                    }
                ],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {
                        "member_id": "B-101",
                        "category": "beam",
                        "story_band_label": "L1",
                        "section_id": 7,
                        "section_name": "H-400x200",
                        "color": "#8aa4d6",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
                "after_segments": [
                    {
                        "member_id": "B-101",
                        "group_id": "L1:perimeter:beam",
                        "action_name": "beam_section_down",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "before_section": "H-400x200",
                        "after_section": "H-350x175",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.9,
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.016,
                        "before_after_snapshot_note": "section H-400x200 -> H-350x175",
                        "color": "#2463eb",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "label": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -18.5,
                        "constructability_delta_sum": -0.3,
                        "max_dcr_after_max": 0.91,
                    }
                ],
                "story_band_rows": [],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_expert_review_issue_metadata.json",
    )

    payload = json.loads(out_summary.read_text(encoding="utf-8"))
    axis_refs = payload["interactive_3d_payload"]["axis_refs"]
    assert payload["interactive_3d_payload"]["axis_ref_source_mode"] == "upstream_named_axis_refs"
    assert axis_refs["x"][0]["label"] == "A"
    assert axis_refs["y"][0]["label"] == "1"
    assert axis_refs["z"][0]["label"] == "L1"


def test_write_review_artifacts_writes_external_expert_review_metadata_bundle(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    expert_metadata_json = tmp_path / "expert_review_issue_metadata.json"
    out_expert_metadata_json = tmp_path / "optimized_drawing_expert_review.metadata.json"

    _write_json(
        expert_metadata_json,
        {
            "project_title": "External Expert Validation Submission",
            "project_number": "EXP-4242",
            "issue_date": "2026-04-10",
            "revision_code": "REV-07",
            "revision_status": "Issued for external validation",
            "jurisdiction": "Seoul Technical Review Office",
            "reviewed_by": "External reviewer",
        },
    )
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "fixture_external_issue_case",
                "case_title": "Fixture External Issue Case",
                "case_note": "external issue metadata should override embedded defaults",
                "status_label": "baseline + ai compare",
            },
            "baseline_structure": {
                "total_element_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#f90'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0af'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='#0a7'/></svg>",
                "member_locator_rows": [
                    {
                        "member_id": "B-101",
                        "member_type": "beam",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "action_name_label": "beam section down",
                        "cost_delta": -12.5,
                        "constructability_delta": -0.15,
                        "selection_gate_label": "hard gate pass",
                        "before_after_snapshot_note": "section A -> B",
                    }
                ],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {
                        "member_id": "B-101",
                        "category": "beam",
                        "story_band_label": "L1",
                        "section_id": 7,
                        "section_name": "H-400x200",
                        "color": "#8aa4d6",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
                "after_segments": [
                    {
                        "member_id": "B-101",
                        "group_id": "L1:perimeter:beam",
                        "action_name": "beam_section_down",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "before_section": "H-400x200",
                        "after_section": "H-350x175",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.9,
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.016,
                        "before_after_snapshot_note": "section H-400x200 -> H-350x175",
                        "color": "#2463eb",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "label": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -18.5,
                        "constructability_delta_sum": -0.3,
                        "max_dcr_after_max": 0.91,
                    }
                ],
                "story_band_rows": [
                    {
                        "story_band": "L1",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -18.5,
                        "constructability_delta_sum": -0.3,
                        "max_dcr_after_max": 0.91,
                    }
                ],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    summary = module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=expert_metadata_json,
        out_expert_metadata_json=out_expert_metadata_json,
    )

    expert_bundle = json.loads(out_expert_metadata_json.read_text(encoding="utf-8"))
    expert_html = tmp_path / "optimized_drawing_expert_review.html"
    expert_text = expert_html.read_text(encoding="utf-8")

    assert summary["output_expert_metadata_json"] == str(out_expert_metadata_json)
    assert expert_bundle["issue_metadata_source_mode"] == "template_metadata_json+external_issue_metadata_json"
    assert expert_bundle["issue_fields"]["project_name"] == "External Expert Validation Submission"
    assert expert_bundle["issue_fields"]["project_number"] == "EXP-4242"
    assert expert_bundle["issue_fields"]["revision_code"] == "REV-07"
    assert expert_bundle["issue_fields"]["revision_status"] == "Issued for external validation"
    assert expert_bundle["issue_fields"]["authority_name"] == "Seoul Technical Review Office"
    assert expert_bundle["issue_fields"]["reviewed_by"] == "External reviewer"
    assert expert_bundle["story_schedule_rows"][0]["reviewer_reason"].startswith("L1 perimeter beam changes cover 1 revision group")
    assert "External Expert Validation Submission" in expert_text
    assert "REV-07" in expert_text
    assert "Issued for external validation" in expert_text


def test_write_review_artifacts_merges_external_metadata_and_case_override(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    expert_metadata_json = tmp_path / "expert_review_issue_metadata.json"

    _write_json(
        expert_metadata_json,
        {
            "project_name": "External Package Title",
            "project_number": "EXT-24010",
            "authority_name": "External Authority",
            "prepared_by": "External Prepared By",
            "revision_code": "REV-X",
        },
    )
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "merge_fixture",
                "case_title": "Merge Fixture",
                "expert_review_metadata": {
                    "project_name": "Inline Override Project",
                    "client_name": "Inline Client",
                    "reviewed_by": "Inline Reviewer",
                },
            },
            "baseline_structure": {
                "total_element_count": 12,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#f90'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#0af'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#0a7'/></svg>",
                "member_locator_rows": [
                    {
                        "member_id": "B-101",
                        "member_type": "beam",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "action_name_label": "beam section down",
                        "cost_delta": -3.2,
                        "constructability_delta": -0.1,
                        "selection_gate_label": "hard gate pass",
                        "before_after_snapshot_note": "section A -> B",
                    }
                ],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {
                        "member_id": "B-101",
                        "category": "beam",
                        "story_band_label": "L1",
                        "section_id": 7,
                        "section_name": "H-400x200",
                        "color": "#8aa4d6",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
                "after_segments": [
                    {
                        "member_id": "B-101",
                        "group_id": "L1:perimeter:beam",
                        "action_name": "beam_section_down",
                        "story_band_label": "L1",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "before_section": "H-400x200",
                        "after_section": "H-350x175",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.9,
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.016,
                        "before_after_snapshot_note": "section H-400x200 -> H-350x175",
                        "color": "#2463eb",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "label": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -3.2,
                        "constructability_delta_sum": -0.1,
                        "max_dcr_after_max": 0.82,
                    }
                ],
                "story_band_rows": [
                    {
                        "story_band": "L1",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -3.2,
                        "constructability_delta_sum": -0.1,
                        "max_dcr_after_max": 0.82,
                    }
                ],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=expert_metadata_json,
    )

    payload = json.loads(out_summary.read_text(encoding="utf-8"))
    merged = payload["expert_review_metadata"]
    assert merged["project_name"] == "Inline Override Project"
    assert merged["project_number"] == "EXT-24010"
    assert merged["client_name"] == "Inline Client"
    assert merged["authority_name"] == "External Authority"
    assert merged["reviewed_by"] == "Inline Reviewer"
    assert merged["prepared_by"] == "External Prepared By"
    assert payload["expert_review_metadata_source_mode"] == "template_metadata_json+external_issue_metadata_json+viewer_case_context_metadata"


def test_write_review_artifacts_supports_project_template_sets(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    template_dir = tmp_path / "expert_review_metadata_templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        template_dir / "index.json",
        {
            "schema_version": "expert_review_metadata_templates.v2",
            "template_set_name": "customer_project_templates",
            "template_set_label": "Customer Project Onboarding Templates",
            "template_set_description": "Template set for customer-facing onboarding intake.",
            "default_template": "default",
            "field_spec": "field_spec.json",
            "project_onboarding_schema": "project_onboarding.schema.json",
            "project_onboarding_example": "project_onboarding.example.json",
            "project_onboarding_purpose": "Customer portal API payload for permit or committee labels.",
            "project_onboarding_sections": [
                "request",
                "project",
                "submission",
                "review_team",
            ],
            "templates": [
                {
                    "name": "permit_city",
                    "path": "permit_city.json",
                    "label": "City Permit Intake",
                    "description": "City permit review onboarding template",
                    "recommended_for": ["City permit package"],
                    "onboarding_focus_fields": [
                        "submission.authority_name",
                        "review_team.reviewed_by",
                    ],
                }
            ],
        },
    )
    _write_json(
        template_dir / "project_onboarding.schema.json",
        {
            "title": "Customer Onboarding Schema",
            "type": "object",
            "properties": {
                "request": {"type": "object"},
                "project": {"type": "object"},
            },
        },
    )
    _write_json(
        template_dir / "project_onboarding.example.json",
        {
            "api_version": "expert_review_onboarding_api.v1",
            "request": {
                "request_id": "REQ-CUST-001",
                "submitted_at": "2026-04-10T09:30:00Z",
                "submitted_by": "customer.portal@example.com",
                "submission_channel": "customer_portal",
                "template_name": "permit_city",
            },
            "project": {
                "project_name": "Customer Example Tower",
                "project_number": "CUST-001",
                "client_name": "Customer Dev",
                "site_name": "Site A",
            },
        },
    )
    _write_json(
        template_dir / "field_spec.json",
        {
            "schema_version": "expert_review_metadata_field_spec.v2",
            "sections": [
                {
                    "section": "project",
                    "fields": [{"name": "project_name", "target_key": "project_name"}],
                }
            ],
        },
    )
    _write_json(
        template_dir / "permit_city.json",
        {
            "authority_name": "Template Authority",
            "permit_label": "Template Permit Review",
            "project_number": "TPL-24010",
            "revision_code": "REV-T",
        },
    )
    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "template_fixture",
                "case_title": "Template Fixture",
                "expert_review_metadata_template": "permit_city",
                "expert_review_metadata": {
                    "project_name": "Inline Template Override",
                    "reviewed_by": "Inline Template Reviewer",
                },
            },
            "baseline_structure": {
                "total_element_count": 8,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#f90'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#0af'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='20' fill='#0a7'/></svg>",
                "member_locator_rows": [],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [],
                "after_segments": [],
            },
            "change_overview": {
                "member_type_rows": [],
                "story_band_rows": [],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_issue_metadata.json",
        expert_metadata_template="default",
        expert_metadata_template_dir=template_dir,
    )

    payload = json.loads(out_summary.read_text(encoding="utf-8"))
    merged = payload["expert_review_metadata"]
    assert merged["project_name"] == "Inline Template Override"
    assert merged["authority_name"] == "Template Authority"
    assert merged["permit_label"] == "Template Permit Review"
    assert merged["project_number"] == "TPL-24010"
    assert merged["revision_code"] == "REV-T"
    assert payload["expert_review_metadata_template"] == "permit_city"
    assert payload["expert_review_metadata_template_path"].endswith("permit_city.json")
    assert payload["expert_review_metadata_template_dir"] == str(template_dir)
    assert payload["expert_review_metadata_template_index_path"] == str(template_dir / "index.json")
    assert payload["expert_review_metadata_template_index_href"] == "expert_review_metadata_templates/index.json"
    assert payload["expert_review_metadata_template_set"]["template_set_label"] == "Customer Project Onboarding Templates"
    assert payload["expert_review_metadata_template_record"]["selected_template_label"] == "City Permit Intake"
    assert payload["expert_review_metadata_template_record"]["selected_template_recommended_for"] == ["City permit package"]
    assert "template=permit_city" in payload["expert_review_metadata_template_selection_receipt"]
    assert "set=Customer Project Onboarding Templates" in payload["expert_review_metadata_template_selection_receipt"]
    assert payload["expert_review_metadata_onboarding_purpose"] == "Customer portal API payload for permit or committee labels."
    assert payload["expert_review_metadata_onboarding_sections"] == [
        "request",
        "project",
        "submission",
        "review_team",
    ]
    assert payload["expert_review_metadata_onboarding_schema_path"].endswith("project_onboarding.schema.json")
    assert payload["expert_review_metadata_onboarding_schema_href"] == "expert_review_metadata_templates/project_onboarding.schema.json"
    assert payload["expert_review_metadata_onboarding_example_path"].endswith("project_onboarding.example.json")
    assert payload["expert_review_metadata_onboarding_example_href"] == "expert_review_metadata_templates/project_onboarding.example.json"
    assert payload["expert_review_metadata_field_spec_path"].endswith("field_spec.json")
    assert payload["expert_review_metadata_field_spec_href"] == "expert_review_metadata_templates/field_spec.json"
    assert payload["expert_review_metadata_source_mode"] == "template_metadata_json+viewer_case_context_metadata"

    expert_bundle = json.loads((tmp_path / "optimized_drawing_expert_review.metadata.json").read_text(encoding="utf-8"))
    assert expert_bundle["issue_metadata_template_dir"] == str(template_dir)
    assert expert_bundle["issue_metadata_field_spec_path"] == str(template_dir / "field_spec.json")
    assert expert_bundle["template_selection"]["selected_template_record"]["selected_template_label"] == "City Permit Intake"
    assert expert_bundle["template_selection"]["template_set"]["template_set_label"] == "Customer Project Onboarding Templates"
    assert expert_bundle["onboarding_artifacts"]["purpose"] == "Customer portal API payload for permit or committee labels."
    assert expert_bundle["onboarding_artifacts"]["sections"] == [
        "request",
        "project",
        "submission",
        "review_team",
    ]
    assert expert_bundle["onboarding_artifacts"]["field_spec_path"] == str(template_dir / "field_spec.json")


def test_all_invalid_geometry_is_traceable_in_summary_and_export_handoff_metadata(tmp_path: Path) -> None:
    module = _load_module()
    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    out_expert_metadata_json = tmp_path / "optimized_drawing_expert_review.metadata.json"

    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "all_invalid_geometry_fixture",
                "case_title": "All Invalid Geometry Fixture",
            },
            "baseline_structure": {
                "total_element_count": 2,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            },
            "member_overlay": {
                "changed_member_count": 1,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "member_locator_rows": [],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [
                    {"member_id": "BAD-BASE", "p0": ["bad", 0, 0], "p1": [1, 1, 1]},
                ],
                "after_segments": [
                    {"member_id": "BAD-AFTER", "p0": [0, 0, 0], "p1": [1, float("inf"), 1]},
                ],
            },
            "change_overview": {
                "member_type_rows": [],
                "story_band_rows": [],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    module.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        out_expert_metadata_json=out_expert_metadata_json,
    )

    summary_payload = json.loads(out_summary.read_text(encoding="utf-8"))
    expected_contract = {
        "coordinate_contract_version": "optimized-review-3d-coordinate-v1",
        "valid_geometry_available": False,
        "no_valid_geometry": True,
        "geometry_status": "no_valid_geometry",
        "valid_point_count": 0,
        "valid_segment_count": 0,
        "invalid_excluded_count": 2,
        "extent_source": "no_valid_geometry",
        "extent_status": "no_valid_geometry",
        "axis_ref_source_mode": "no_valid_geometry",
        "coordinate_contract_valid": False,
    }
    assert summary_payload["interactive_3d_geometry_contract"] == expected_contract
    assert summary_payload["interactive_3d_coordinate_contract_validation"]["no_valid_geometry"] is True

    expert_bundle = json.loads(out_expert_metadata_json.read_text(encoding="utf-8"))
    assert expert_bundle["summary"]["interactive_3d_geometry_contract"] == expected_contract
    assert expert_bundle["export_handoff_contracts"]["interactive_3d_geometry_contract"] == expected_contract


def test_generated_release_summary_and_expert_metadata_keep_delivery_contract_freshness(tmp_path: Path) -> None:
    module = _load_module()
    release_summary_path, release_metadata_path = _write_delivery_contract_fixture(tmp_path, module)

    release_summary = json.loads(release_summary_path.read_text(encoding="utf-8"))
    release_metadata = json.loads(release_metadata_path.read_text(encoding="utf-8"))

    _assert_delivery_contract_core(release_summary)
    _assert_delivery_contract_core(release_metadata)
    rebuilt_contracts = module._build_export_handoff_contracts(release_summary)
    assert (
        release_summary["export_handoff_contracts"]["archive_handoff_contract"]["artifact_href_validation_summary"]
        == rebuilt_contracts["archive_handoff_contract"]["artifact_href_validation_summary"]
    )
    assert release_metadata["export_handoff_contracts"] == release_summary["export_handoff_contracts"]
    assert release_metadata["story_schedule_rows"] == release_summary["story_schedule_rows"]
    assert (
        release_metadata["representative_evidence_completeness_summary"]
        == release_summary["representative_evidence_completeness_summary"]
    )


def test_generated_release_summary_and_metadata_expose_project_package_membership_freshness_contract(tmp_path: Path) -> None:
    module = _load_module()
    release_summary_path, release_metadata_path = _write_delivery_contract_fixture(tmp_path, module)

    release_summary = json.loads(release_summary_path.read_text(encoding="utf-8"))
    release_metadata = json.loads(release_metadata_path.read_text(encoding="utf-8"))

    _assert_project_package_freshness_contract(
        release_summary,
        release_visualization_dir=release_summary_path.parent,
    )
    _assert_project_package_zip_members(
        release_summary,
        release_visualization_dir=release_summary_path.parent,
    )
    _assert_project_package_freshness_contract(
        release_metadata,
        release_visualization_dir=release_summary_path.parent,
    )
    _assert_project_package_zip_members(
        release_metadata,
        release_visualization_dir=release_summary_path.parent,
    )


def test_default_onboarding_artifacts_use_customer_portal_api_payload() -> None:
    module = _load_module()
    template_dir = Path(module.DEFAULT_EXPERT_METADATA_TEMPLATE_DIR)
    index_payload = json.loads((template_dir / "index.json").read_text(encoding="utf-8"))
    schema_payload = json.loads((template_dir / "project_onboarding.schema.json").read_text(encoding="utf-8"))
    example_payload = json.loads((template_dir / "project_onboarding.example.json").read_text(encoding="utf-8"))
    field_spec_payload = json.loads((template_dir / "field_spec.json").read_text(encoding="utf-8"))

    assert index_payload["field_spec"] == "field_spec.json"
    assert index_payload["web_form_contract"]["form_id"] == "expert-review-onboarding-form-v1"
    assert index_payload["backend_dto_contract"]["dto_name"] == "ExpertReviewOnboardingRequestDto"
    assert index_payload["project_onboarding_sections"] == [
        "request",
        "project",
        "submission",
        "review_team",
        "review_labels",
        "reviewer_guidance",
        "metadata_overrides",
    ]
    assert set(schema_payload["required"]) == {
        "api_version",
        "request",
        "project",
        "submission",
        "review_team",
    }
    assert schema_payload["x-web-form-id"] == "expert-review-onboarding-form-v1"
    assert schema_payload["x-backend-dto"] == "ExpertReviewOnboardingRequestDto"
    assert schema_payload["properties"]["request"]["properties"]["submission_channel"]["enum"] == [
        "customer_portal",
        "sales_ops",
        "api_import",
    ]
    assert schema_payload["properties"]["request"]["properties"]["template_name"]["enum"] == [
        "default",
        "seoul_permit_review",
        "structural_peer_committee",
    ]
    assert example_payload["request"]["template_name"] == "seoul_permit_review"
    assert example_payload["api_version"] == "expert_review_onboarding_api.v1"
    assert "project" in example_payload
    assert "submission" in example_payload
    assert "review_team" in example_payload
    assert "metadata_overrides" in example_payload
    assert field_spec_payload["sections"][0]["section"] == "request"
    assert field_spec_payload["web_form_id"] == "expert-review-onboarding-form-v1"
    assert field_spec_payload["backend_dto"] == "ExpertReviewOnboardingRequestDto"
    assert field_spec_payload["sections"][0]["fields"][2]["dto_field"] == "request.requestId"
    assert field_spec_payload["sections"][-1]["section"] == "metadata_overrides"
