from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_midas_native_writeback_diff_receipts import _infer_structure_type


SCRIPT = Path("implementation/phase1/generate_midas_native_writeback_diff_receipts.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_midas_native_writeback_diff_receipts_passes_for_stable_writeback(tmp_path: Path) -> None:
    out_dir = tmp_path / "receipts"
    out = out_dir / "midas_native_writeback_diff_receipts_report.json"
    source_mgt = tmp_path / "source.mgt"
    writeback_mgt = tmp_path / "writeback.mgt"
    source_mgt.write_text("*NODE\n", encoding="utf-8")
    writeback_mgt.write_text("*NODE\n*ENDDATA\n", encoding="utf-8")
    source_conversion = tmp_path / "source_conversion.json"
    writeback_roundtrip = tmp_path / "writeback_roundtrip.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip.json"
    corpus_manifest = tmp_path / "corpus_manifest.json"

    source_metrics = {
        "section_count": 33,
        "node_count": 100,
        "element_count": 120,
        "beam_element_count": 50,
        "shell_element_count": 70,
        "member_row_count": 10,
        "group_row_count": 2,
        "design_section_row_count": 5,
        "static_load_case_count": 6,
        "load_combination_row_count": 8,
        "nodal_load_row_count": 12,
        "pressure_load_row_count": 40,
        "selfweight_row_count": 1,
        "typed_row_total": 500,
        "thickness_row_count": 19,
        "section_scale_row_count": 0,
        "unknown_row_total": 0,
    }
    writeback_metrics = dict(source_metrics)
    writeback_metrics.update({"typed_row_total": 516, "thickness_row_count": 34})
    _write_json(source_conversion, {"metrics": source_metrics})
    _write_json(writeback_roundtrip, {"metrics": writeback_metrics})
    _write_json(
        export_report,
        {
            "summary": {
                "direct_patch_change_count": 25,
                "audit_review_queue_pending_count": 2,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_roundtrip_pass": True,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(
        loadcomb_roundtrip,
        {
            "pass": True,
            "exact_entry_row_coverage": 1.0,
            "exact_header_coverage": 1.0,
            "exact_factor_map_coverage": 1.0,
        },
    )
    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "cases": [
                {
                    "case_id": "native_case__optimized_writeback",
                    "role": "native_writeback",
                    "native_writeback_ready": True,
                    "artifacts": {
                        "source_mgt": {"path": str(source_mgt), "exists": True},
                        "source_conversion_report": {"path": str(source_conversion), "exists": True},
                        "writeback_mgt": {"path": str(writeback_mgt), "exists": True},
                        "writeback_roundtrip_report": {"path": str(writeback_roundtrip), "exists": True},
                        "export_report": {"path": str(export_report), "exists": True},
                        "patch_manifest": {"path": str(patch_manifest), "exists": True},
                        "loadcomb_roundtrip_report": {"path": str(loadcomb_roundtrip), "exists": True},
                    },
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["receipt_pass_count"] == 1
    assert payload["summary"]["loadcomb_exact_case_count"] == 1
    assert payload["summary"]["structure_type_batch_count"] == 1
    assert payload["summary"]["taxonomy_case_counts"]["canonical_rewrite"] == 1
    assert (out_dir / "unsupported_lossy_card_family_appendix.md").exists()
    assert (out_dir / "unsupported_lossy_card_family_appendix.json").exists()
    assert payload["unsupported_lossy_card_family_appendix_markdown"].endswith(
        "unsupported_lossy_card_family_appendix.md"
    )
    assert payload["unsupported_lossy_card_family_appendix_json"].endswith(
        "unsupported_lossy_card_family_appendix.json"
    )
    assert len(payload["receipt_rows"]) == 1
    assert payload["receipt_rows"][0]["taxonomy"]["labels"] == ["canonical_rewrite", "manual_review_required"]


def test_generate_midas_native_writeback_diff_receipts_writes_exact_topology_structural_preview_queue(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "receipts"
    out = out_dir / "midas_native_writeback_diff_receipts_report.json"
    corpus_manifest = tmp_path / "corpus_manifest.json"
    korean_source_catalog = tmp_path / "korean_source_catalog.json"
    source_mgt = tmp_path / "source.mgt"
    writeback_mgt = tmp_path / "writeback.mgt"
    source_conversion = tmp_path / "source_conversion.json"
    writeback_roundtrip = tmp_path / "writeback_roundtrip.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip.json"
    source_mgt.write_text("*NODE\n", encoding="utf-8")
    writeback_mgt.write_text("*NODE\n*ENDDATA\n", encoding="utf-8")
    source_metrics = {
        "section_count": 1,
        "node_count": 1,
        "element_count": 0,
        "beam_element_count": 0,
        "shell_element_count": 0,
        "member_row_count": 0,
        "group_row_count": 0,
        "design_section_row_count": 0,
        "static_load_case_count": 0,
        "load_combination_row_count": 0,
        "nodal_load_row_count": 0,
        "pressure_load_row_count": 0,
        "selfweight_row_count": 0,
        "typed_row_total": 1,
        "thickness_row_count": 0,
        "section_scale_row_count": 0,
        "unknown_row_total": 0,
    }
    _write_json(source_conversion, {"metrics": source_metrics})
    _write_json(writeback_roundtrip, {"metrics": dict(source_metrics)})
    _write_json(
        export_report,
        {
            "summary": {
                "direct_patch_change_count": 0,
                "audit_review_queue_pending_count": 0,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_roundtrip_pass": True,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(
        loadcomb_roundtrip,
        {
            "pass": True,
            "exact_entry_row_coverage": 1.0,
            "exact_header_coverage": 1.0,
            "exact_factor_map_coverage": 1.0,
        },
    )

    _write_json(
        korean_source_catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "exact_topology_candidate": True,
                    "native_writeback_candidate": False,
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                }
            ],
        },
    )

    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "korean_structural_preview_candidate_rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "candidate_origin": "korean_source_catalog",
                    "source_class": "ifc_public",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "structure_type": "building",
                    "promotion_target": "public_structural_preview",
                    "promotion_flow": "derived_structural_preview_candidate",
                    "promotion_status": "pending_solver_ready_reconstruction",
                    "promotion_blocker": "ifc_structural_subset_requires_solver_ready_reconstruction",
                    "structural_preview_case_id": "ifc_public_award_structure__structural_preview_candidate",
                    "structural_preview_writeback_case_id": "ifc_public_award_structure__structural_preview_candidate__identity_writeback",
                    "solver_ready_reconstruction_artifact_json": str(
                        tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.json"
                    ),
                    "solver_ready_reconstruction_artifact_markdown": str(
                        tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.md"
                    ),
                    "native_writeback_candidate": False,
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                    "download_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                }
            ],
            "cases": [
                {
                    "case_id": "fixture_case__identity_writeback",
                    "role": "native_writeback_fixture_derived",
                    "native_writeback_ready": True,
                    "structure_type": "foundation",
                    "writeback_mode": "canonical_fixture_identity_baseline",
                    "artifacts": {
                        "source_mgt": {"path": str(source_mgt), "exists": True},
                        "source_conversion_report": {"path": str(source_conversion), "exists": True},
                        "writeback_mgt": {"path": str(writeback_mgt), "exists": True},
                        "writeback_roundtrip_report": {"path": str(writeback_roundtrip), "exists": True},
                        "export_report": {"path": str(export_report), "exists": True},
                        "patch_manifest": {"path": str(patch_manifest), "exists": True},
                        "loadcomb_roundtrip_report": {"path": str(loadcomb_roundtrip), "exists": True},
                    },
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--korean-source-catalog",
            str(korean_source_catalog),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["exact_topology_structural_preview_candidate_total"] == 1
    assert payload["summary"]["exact_topology_structural_preview_pending_candidate_count"] == 1
    assert payload["summary"]["exact_topology_structural_preview_korean_candidate_total"] == 1
    assert payload["summary"]["korean_structural_preview_promotion_receipt_count"] == 1
    assert payload["summary_line"].find("exact_queue=1/1") != -1
    assert payload["summary_line"].find("korean_promotions=1/1") != -1
    assert payload["exact_topology_structural_preview_promotion_queue_json"].endswith(
        "exact_topology_structural_preview_promotion_queue.json"
    )
    assert payload["exact_topology_structural_preview_promotion_queue_markdown"].endswith(
        "exact_topology_structural_preview_promotion_queue.md"
    )
    assert len(payload["exact_topology_structural_preview_pending_candidate_rows"]) == 1
    queue_json = json.loads(
        Path(payload["exact_topology_structural_preview_promotion_queue_json"]).read_text(encoding="utf-8")
    )
    assert queue_json["summary"]["candidate_total"] == 1
    assert queue_json["summary"]["pending_candidate_count"] == 1
    assert queue_json["summary"]["korean_pending_candidate_count"] == 1
    assert queue_json["pending_candidate_rows"][0]["source_id"] == "ifc_public_award_structure"
    assert queue_json["pending_candidate_rows"][0]["structural_preview_case_id"] == (
        "ifc_public_award_structure__structural_preview_candidate"
    )
    assert queue_json["pending_candidate_rows"][0]["promotion_receipt_json"].endswith(
        "ifc_public_award_structure.structural_preview_promotion_receipt.json"
    )
    assert len(payload["korean_structural_preview_promotion_receipt_rows"]) == 1
    receipt_path = Path(
        payload["korean_structural_preview_promotion_receipt_rows"][0]["promotion_receipt_json"]
    )
    assert receipt_path.exists()
    receipt_json = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt_json["source_id"] == "ifc_public_award_structure"
    assert receipt_json["structural_preview_case_id"] == (
        "ifc_public_award_structure__structural_preview_candidate"
    )
    assert receipt_json["promotion_status"] == "pending_solver_ready_reconstruction"
    assert receipt_json["solver_ready_reconstruction_artifact_json"].endswith(
        "ifc_public_award_structure.solver_ready_reconstruction.json"
    )
    assert receipt_json["summary"]["solver_ready_reconstruction_artifact_present"] is True


def test_infer_structure_type_promotes_stair_before_vertical_circulation() -> None:
    assert (
        _infer_structure_type(
            {
                "case_id": "gtc_public_bridge_bearing_c04__identity_writeback",
                "source_family": "gtc_public_bridge_bearing",
            }
        )
        == "bearing"
    )
    assert (
        _infer_structure_type(
            {
                "case_id": "gtc_public_bridge_section_e1_03__identity_writeback",
                "source_family": "gtc_public_bridge_section",
            }
        )
        == "bridge_section"
    )
    assert (
        _infer_structure_type(
            {
                "case_id": "midas_support_beam_archive__bridge_native__identity_writeback",
                "source_family": "midas_support_attachment_bridge_baseline",
            }
        )
        == "beam"
    )
    assert (
        _infer_structure_type(
            {
                "case_id": "midas_support_stair_archive__decoded_preview_native__identity_writeback",
                "source_family": "midas_support_attachment_decoded_preview",
            }
        )
        == "stair"
    )
    assert (
        _infer_structure_type(
            {
                "case_id": "midas_support_ramp_archive__decoded_preview_native__identity_writeback",
                "source_family": "midas_support_attachment_decoded_preview",
            }
        )
        == "ramp"
    )


def test_generate_midas_native_writeback_diff_receipts_bootstraps_public_bridge_identity_baseline(tmp_path: Path) -> None:
    out_dir = tmp_path / "receipts"
    out = out_dir / "midas_native_writeback_diff_receipts_report.json"
    generated_dir = tmp_path / "generated" / "beam_bridge_native"
    source_mgt = generated_dir / "midas_support_beam_archive__bridge_native.mgt"
    writeback_mgt = generated_dir / "midas_support_beam_archive__bridge_native.identity_writeback.mgt"
    source_conversion = generated_dir / "source_conversion_report.json"
    writeback_roundtrip = generated_dir / "writeback_roundtrip_report.json"
    export_report = generated_dir / "fixture_export_report.json"
    patch_manifest = generated_dir / "fixture_patch_manifest.json"
    loadcomb_roundtrip = generated_dir / "fixture_loadcomb_roundtrip_report.json"
    bridge_model = tmp_path / "bridge_model.json"
    bridge_report = tmp_path / "bridge_report.json"
    corpus_manifest = tmp_path / "corpus_manifest.json"

    _write_json(
        bridge_model,
        {
            "model": {
                "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}, {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0}],
                "elements": [{"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2]}],
                "materials": [],
                "sections": [],
            },
            "topology_metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1, "shell_element_count": 0},
        },
    )
    _write_json(
        bridge_report,
        {
            "summary": {
                "viewer_ready": True,
                "family_assumption": "beam",
                "node_count": 2,
                "element_count": 1,
                "member_id_count": 1,
            }
        },
    )
    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "cases": [
                {
                    "case_id": "midas_support_beam_archive__bridge_native__identity_writeback",
                    "source_id": "midas_support_beam_archive",
                    "role": "native_writeback_public_bridge_derived",
                    "native_writeback_ready": True,
                    "structure_type": "beam",
                    "writeback_mode": "public_bridge_identity_baseline",
                    "artifacts": {
                        "source_mgt": {"path": str(source_mgt), "exists": False},
                        "source_conversion_report": {"path": str(source_conversion), "exists": False},
                        "writeback_mgt": {"path": str(writeback_mgt), "exists": False},
                        "writeback_roundtrip_report": {"path": str(writeback_roundtrip), "exists": False},
                        "export_report": {"path": str(export_report), "exists": False},
                        "patch_manifest": {"path": str(patch_manifest), "exists": False},
                        "loadcomb_roundtrip_report": {"path": str(loadcomb_roundtrip), "exists": False},
                        "bridge_model_json": {"path": str(bridge_model), "exists": True},
                        "bridge_report": {"path": str(bridge_report), "exists": True},
                    },
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["ready_case_count"] == 1
    assert payload["summary"]["structure_type_batch_count"] == 1
    assert payload["receipt_rows"][0]["structure_type"] == "beam"
    assert payload["receipt_rows"][0]["taxonomy"]["labels"] == ["preserved_exact", "public_bridge_baseline"]
    assert source_mgt.exists()
    assert writeback_mgt.exists()


def test_generate_midas_native_writeback_diff_receipts_bootstraps_public_raw_identity_baseline(tmp_path: Path) -> None:
    out_dir = tmp_path / "receipts"
    out = out_dir / "midas_native_writeback_diff_receipts_report.json"
    generated_dir = tmp_path / "generated" / "gtc_public_bridge_bearing_c04"
    source_mgt = tmp_path / "gtc_public_bridge_bearing_c04.mgt"
    source_mgt.write_text(
        "\n".join(
            [
                "*NODE",
                "1,0,0,0",
                "2,1,0,0",
                "3,2,0,0",
                "4,3,0,0",
                "5,4,0,0",
                "6,5,0,0",
                "7,6,0,0",
                "8,7,0,0",
                "*ELEMENT",
                "1,BEAM,1,2",
                "2,BEAM,3,4",
                "3,BEAM,5,6",
                "4,BEAM,7,8",
                "*ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )
    source_conversion = generated_dir / "source_conversion_report.json"
    writeback_mgt = generated_dir / "gtc_public_bridge_bearing_c04.identity_writeback.mgt"
    writeback_roundtrip = generated_dir / "writeback_roundtrip_report.json"
    export_report = generated_dir / "fixture_export_report.json"
    patch_manifest = generated_dir / "fixture_patch_manifest.json"
    loadcomb_roundtrip = generated_dir / "fixture_loadcomb_roundtrip_report.json"
    corpus_manifest = tmp_path / "corpus_manifest.json"

    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "cases": [
                {
                    "case_id": "gtc_public_bridge_bearing_c04__identity_writeback",
                    "source_id": "gtc_public_bridge_bearing_c04",
                    "role": "native_writeback_public_raw_derived",
                    "native_writeback_ready": True,
                    "writeback_mode": "public_raw_identity_baseline",
                    "artifacts": {
                        "source_mgt": {"path": str(source_mgt), "exists": True},
                        "source_conversion_report": {"path": str(source_conversion), "exists": False},
                        "writeback_mgt": {"path": str(writeback_mgt), "exists": False},
                        "writeback_roundtrip_report": {"path": str(writeback_roundtrip), "exists": False},
                        "export_report": {"path": str(export_report), "exists": False},
                        "patch_manifest": {"path": str(patch_manifest), "exists": False},
                        "loadcomb_roundtrip_report": {"path": str(loadcomb_roundtrip), "exists": False},
                    },
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["ready_case_count"] == 1
    assert payload["receipt_rows"][0]["structure_type"] == "bearing"
    assert payload["receipt_rows"][0]["writeback_mode"] == "public_raw_identity_baseline"
    assert payload["receipt_rows"][0]["taxonomy"]["labels"] == ["preserved_exact", "public_raw_native"]
    assert source_conversion.exists()
    assert writeback_mgt.exists()
    assert writeback_roundtrip.exists()


def test_generate_midas_native_writeback_diff_receipts_allows_preserved_unknown_rows_for_public_raw_identity(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "receipts"
    out = out_dir / "midas_native_writeback_diff_receipts_report.json"
    source_mgt = tmp_path / "gtc_public_bridge_section_a3.mgt"
    writeback_mgt = tmp_path / "gtc_public_bridge_section_a3.identity_writeback.mgt"
    source_mgt.write_text("*NODE\n", encoding="utf-8")
    writeback_mgt.write_text("*NODE\n*ENDDATA\n", encoding="utf-8")
    source_conversion = tmp_path / "source_conversion.json"
    writeback_roundtrip = tmp_path / "writeback_roundtrip.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip.json"
    corpus_manifest = tmp_path / "corpus_manifest.json"

    metrics = {
        "section_count": 12,
        "node_count": 150,
        "element_count": 147,
        "beam_element_count": 147,
        "shell_element_count": 0,
        "member_row_count": 0,
        "group_row_count": 0,
        "design_section_row_count": 0,
        "static_load_case_count": 14,
        "load_combination_row_count": 2,
        "nodal_load_row_count": 664,
        "pressure_load_row_count": 0,
        "selfweight_row_count": 0,
        "typed_row_total": 700,
        "thickness_row_count": 0,
        "section_scale_row_count": 0,
        "unknown_row_total": 273,
    }
    _write_json(source_conversion, {"metrics": metrics})
    _write_json(writeback_roundtrip, {"metrics": metrics})
    _write_json(
        export_report,
        {
            "summary": {
                "direct_patch_change_count": 0,
                "audit_review_queue_pending_count": 0,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_roundtrip_pass": True,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(
        loadcomb_roundtrip,
        {
            "pass": True,
            "exact_entry_row_coverage": 1.0,
            "exact_header_coverage": 1.0,
            "exact_factor_map_coverage": 1.0,
        },
    )
    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "cases": [
                {
                    "case_id": "gtc_public_bridge_section_a3__identity_writeback",
                    "role": "native_writeback_public_raw_derived",
                    "native_writeback_ready": True,
                    "writeback_mode": "public_raw_identity_baseline",
                    "artifacts": {
                        "source_mgt": {"path": str(source_mgt), "exists": True},
                        "source_conversion_report": {"path": str(source_conversion), "exists": True},
                        "writeback_mgt": {"path": str(writeback_mgt), "exists": True},
                        "writeback_roundtrip_report": {"path": str(writeback_roundtrip), "exists": True},
                        "export_report": {"path": str(export_report), "exists": True},
                        "patch_manifest": {"path": str(patch_manifest), "exists": True},
                        "loadcomb_roundtrip_report": {"path": str(loadcomb_roundtrip), "exists": True},
                    },
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--out-dir",
            str(out_dir),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["receipt_rows"][0]["contract_pass"] is True
    assert payload["receipt_rows"][0]["unknown_rows_zero_pass"] is True
    assert payload["receipt_rows"][0]["taxonomy"]["labels"] == [
        "preserved_exact",
        "public_raw_native",
        "unknown_rows_preserved_public_raw",
    ]
