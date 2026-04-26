from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_midas_native_corpus_manifest import (
    _append_public_archive_structural_preview_rows,
    _append_public_bridge_baseline_rows,
    _bridge_baseline_structure_type,
    _infer_structure_type,
    _preview_structure_type,
)


SCRIPT = Path("implementation/phase1/generate_midas_native_corpus_manifest.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generate_midas_native_corpus_manifest_builds_honest_manifest(tmp_path: Path) -> None:
    source_mgt = tmp_path / "model.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    writeback_mgt = tmp_path / "model.optimized.mgt"
    writeback_mgt.write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")

    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_conversion = tmp_path / "midas_mgt_conversion_report.json"
    writeback_roundtrip = tmp_path / "roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    public_catalog = tmp_path / "missing_public_native_mgt_source_catalog.json"
    public_report = tmp_path / "missing_public_native_corpus_report.json"
    korean_catalog = tmp_path / "missing_korean_source_catalog.json"
    reconstruction_report = tmp_path / "missing_korean_solver_ready_reconstruction_report.json"
    fixture_dir = tmp_path / "empty_fixtures"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"

    source_sha = _sha256(source_mgt)
    _write_json(
        quality_catalog,
        {
            "sources": [
                {"source_id": "native_case", "source_family": "github_real_export", "source_class": "mgt_text"},
                {"source_id": "archive_case", "source_family": "midas_archive_bundle", "source_class": "midas_archive"},
            ]
        },
    )
    _write_json(
        quality_report,
        {
            "contract_pass": True,
            "summary": {
                "accepted_parseable_count": 1,
                "accepted_archive_count": 1,
                "recognized_archive_member_total": 3,
            },
            "accepted": [
                {
                    "source_id": "native_case",
                    "source_class": "mgt_text",
                    "sha256": source_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"mgt": str(source_mgt)},
                    "metrics": {"node_count": 1, "element_count": 0},
                },
                {
                    "source_id": "archive_case",
                    "source_class": "midas_archive",
                    "sha256": "archive",
                    "parse_ok": False,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"archive_members": ["A.mgt", "B.mgt"]},
                    "metrics": {"recognized_midas_member_count": 2},
                },
            ],
        },
    )
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {
            "summary": {
                "audit_review_queue_pending_count": 2,
                "direct_patch_change_count": 25,
                "direct_patch_action_family_counts": {"section": 1},
                "loadcomb_roundtrip_pass": True,
                "output_mgt_exists": True,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_combo_count": 8,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(reconstruction_report),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(fixture_dir),
            "--generated-root",
            str(generated_root),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode in {0, 1}, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["actual_source_count"] == 2
    assert payload["summary"]["corpus_case_count"] == 3
    assert payload["summary"]["native_writeback_ready_count"] == 1
    assert payload["summary"]["public_native_writeback_ready_count"] == 1
    assert payload["summary"]["public_archive_preview_text_case_count"] == 0
    assert payload["summary"]["public_archive_preview_writeback_ready_count"] == 0
    assert payload["summary"]["public_source_writeback_ready_count"] == 1
    assert payload["summary"]["fixture_native_writeback_ready_count"] == 0
    assert payload["summary"]["source_family_count"] == 2


def test_generate_midas_native_corpus_manifest_merges_public_raw_native_sources(tmp_path: Path) -> None:
    source_mgt = tmp_path / "model.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    writeback_mgt = tmp_path / "model.optimized.mgt"
    writeback_mgt.write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")
    public_raw_mgt = tmp_path / "gtc_public_bridge_bearing_c04.mgt"
    public_raw_mgt.write_text("*NODE\n1,0,0,0\n2,1,0,0\n*ELEMENT\n1,BEAM,1,2\n*ENDDATA\n", encoding="utf-8")

    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    public_catalog = tmp_path / "public_native_mgt_source_catalog.json"
    public_report = tmp_path / "public_native_corpus_report.json"
    korean_catalog = tmp_path / "missing_korean_source_catalog.json"
    reconstruction_report = tmp_path / "missing_korean_solver_ready_reconstruction_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_conversion = tmp_path / "midas_mgt_conversion_report.json"
    writeback_roundtrip = tmp_path / "roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    public_conversion = tmp_path / "gtc_public_bridge_bearing_c04_conversion_report.json"
    fixture_dir = tmp_path / "empty_fixtures"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"

    source_sha = _sha256(source_mgt)
    public_sha = _sha256(public_raw_mgt)
    _write_json(
        quality_catalog,
        {
            "sources": [
                {"source_id": "native_case", "source_family": "github_real_export", "source_class": "mgt_text"},
                {"source_id": "archive_case", "source_family": "midas_archive_bundle", "source_class": "midas_archive"},
            ]
        },
    )
    _write_json(
        quality_report,
        {
            "contract_pass": True,
            "summary": {
                "accepted_parseable_count": 1,
                "accepted_archive_count": 1,
                "recognized_archive_member_total": 1,
            },
            "accepted": [
                {
                    "source_id": "native_case",
                    "source_class": "mgt_text",
                    "sha256": source_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"mgt": str(source_mgt)},
                    "metrics": {"node_count": 1, "element_count": 0},
                },
                {
                    "source_id": "archive_case",
                    "source_class": "midas_archive",
                    "sha256": "archive",
                    "parse_ok": False,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"archive_members": ["A.mgt"]},
                    "metrics": {"recognized_midas_member_count": 1},
                },
            ],
        },
    )
    _write_json(
        public_catalog,
        {
            "sources": [
                {
                    "source_id": "gtc_public_bridge_bearing_c04",
                    "source_family": "gtc_public_bridge_bearing",
                    "source_class": "mgt_text",
                    "provenance": "gtc_public_file_get",
                    "structure_type": "bearing",
                }
            ]
        },
    )
    _write_json(
        public_conversion,
        {
            "metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1, "typed_row_total": 3},
            "contract_pass": True,
        },
    )
    _write_json(
        public_report,
        {
            "contract_pass": True,
            "summary": {"accepted_parseable_count": 1, "accepted_count": 1},
            "accepted": [
                {
                    "source_id": "gtc_public_bridge_bearing_c04",
                    "source_class": "mgt_text",
                    "sha256": public_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {
                        "mgt": str(public_raw_mgt),
                        "conversion_report": str(public_conversion),
                    },
                    "metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1},
                }
            ],
        },
    )
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {
            "summary": {
                "audit_review_queue_pending_count": 0,
                "direct_patch_change_count": 0,
                "direct_patch_action_family_counts": {},
                "loadcomb_roundtrip_pass": True,
                "output_mgt_exists": True,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_combo_count": 0,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(reconstruction_report),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(fixture_dir),
            "--generated-root",
            str(generated_root),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode in {0, 1}, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["actual_source_count"] == 3
    assert payload["summary"]["quality_actual_source_count"] == 2
    assert payload["summary"]["public_raw_actual_source_count"] == 1
    assert payload["summary"]["public_native_text_case_count"] == 2
    assert payload["summary"]["public_raw_native_text_case_count"] == 1
    assert payload["summary"]["public_native_writeback_ready_count"] == 2
    assert payload["summary"]["public_raw_native_writeback_ready_count"] == 1
    assert payload["summary"]["public_source_writeback_ready_count"] == 2
    raw_writeback = next(
        row for row in payload["cases"] if row["role"] == "native_writeback_public_raw_derived"
    )
    assert raw_writeback["structure_type"] == "bearing"
    assert raw_writeback["writeback_mode"] == "public_raw_identity_baseline"


def test_generate_midas_native_corpus_manifest_tracks_korean_source_catalog(tmp_path: Path) -> None:
    source_mgt = tmp_path / "model.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    writeback_mgt = tmp_path / "model.optimized.mgt"
    writeback_mgt.write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")

    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_conversion = tmp_path / "midas_mgt_conversion_report.json"
    writeback_roundtrip = tmp_path / "roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    public_catalog = tmp_path / "missing_public_native_mgt_source_catalog.json"
    public_report = tmp_path / "missing_public_native_corpus_report.json"
    korean_catalog = tmp_path / "korean_source_catalog.json"
    reconstruction_report = tmp_path / "missing_korean_solver_ready_reconstruction_report.json"
    fixture_dir = tmp_path / "empty_fixtures"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"

    source_sha = _sha256(source_mgt)
    _write_json(
        quality_catalog,
        {
            "sources": [
                {"source_id": "native_case", "source_family": "github_real_export", "source_class": "mgt_text"},
                {"source_id": "archive_case", "source_family": "midas_archive_bundle", "source_class": "midas_archive"},
            ]
        },
    )
    _write_json(
        quality_report,
        {
            "contract_pass": True,
            "summary": {
                "accepted_parseable_count": 1,
                "accepted_archive_count": 1,
                "recognized_archive_member_total": 1,
            },
            "accepted": [
                {
                    "source_id": "native_case",
                    "source_class": "mgt_text",
                    "sha256": source_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"mgt": str(source_mgt)},
                    "metrics": {"node_count": 1, "element_count": 0},
                },
                {
                    "source_id": "archive_case",
                    "source_class": "midas_archive",
                    "sha256": "archive",
                    "parse_ok": False,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"archive_members": ["A.mgt"]},
                    "metrics": {"recognized_midas_member_count": 1},
                },
            ],
        },
    )
    _write_json(
        korean_catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "koneps_public_building_rc",
                    "title": "KONEPS public building",
                    "source_class": "koneps",
                    "origin_type": "public_notice_attachment",
                    "format": "mgt",
                    "content_kind": "native_text_model",
                    "provenance_url": "https://example.go.kr/a.mgt",
                },
                {
                    "source_id": "lh_sh_standard_housing_base",
                    "title": "LH standard housing base",
                    "source_class": "lh_sh",
                    "origin_type": "competition_base_material",
                    "format": "zip",
                    "content_kind": "archive_bundle",
                    "provenance_url": "https://example.lh.or.kr/b.zip",
                },
                {
                    "source_id": "aik_kci_kds_design_example",
                    "title": "KDS design example",
                    "source_class": "aik_kci",
                    "origin_type": "society_example_appendix",
                    "format": "pdf",
                    "content_kind": "structural_report",
                    "provenance_url": "https://example.kci.or.kr/c.pdf",
                },
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "provenance_url": "https://example.bim.or.kr/d.ifc",
                    "exact_topology_candidate": True,
                    "collection_policy": "local_first_manual_attach",
                    "curated_local_ifc_required": True,
                    "curated_local_ifc_status": "required_missing",
                },
            ],
        },
    )
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {
            "summary": {
                "audit_review_queue_pending_count": 0,
                "direct_patch_change_count": 0,
                "direct_patch_action_family_counts": {},
                "loadcomb_roundtrip_pass": True,
                "output_mgt_exists": True,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_combo_count": 0,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(reconstruction_report),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(fixture_dir),
            "--generated-root",
            str(generated_root),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert out.exists(), proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["korean_source_catalog_record_count"] == 4
    assert payload["summary"]["korean_source_catalog_source_class_counts"] == {
        "aik_kci": 1,
        "ifc_public": 1,
        "koneps": 1,
        "lh_sh": 1,
    }
    assert payload["summary"]["korean_source_catalog_exact_topology_candidate_count"] == 1
    assert payload["summary"]["korean_source_catalog_exact_topology_candidate_pending_count"] == 1
    assert payload["summary"]["korean_source_catalog_native_writeback_candidate_count"] == 0
    assert payload["korean_exact_topology_candidate_rows"] == [
        {
            "source_id": "ifc_public_award_structure",
            "title": "IFC award structure",
            "source_class": "ifc_public",
            "origin_type": "bim_award_archive",
            "origin_org": "",
            "format": "ifc",
            "content_kind": "ifc_structural_subset",
            "structure_type": "",
            "structural_system": "",
            "storey_band": "",
            "ingest_status": "",
            "provenance_url": "https://example.bim.or.kr/d.ifc",
            "download_url": "",
            "native_writeback_candidate": False,
            "exact_topology_candidate": True,
            "curated_local_ifc_required": True,
            "curated_local_ifc_status": "required_missing",
            "curated_local_ifc_reference": "",
            "promotion_target": "public_structural_preview",
            "status": "pending_solver_ready_reconstruction",
            "blocker": "curated_local_ifc_reference_required",
            "solver_ready_reconstruction_artifact_json": "",
            "solver_ready_reconstruction_artifact_markdown": "",
            "solver_ready_reconstruction_summary_line": "",
        }
    ]
    assert payload["summary"]["korean_structural_preview_candidate_count"] == 1
    assert payload["korean_structural_preview_candidate_rows"] == [
        {
            "source_id": "ifc_public_award_structure",
            "title": "IFC award structure",
            "candidate_origin": "korean_source_catalog",
            "source_class": "ifc_public",
            "format": "ifc",
            "content_kind": "ifc_structural_subset",
            "structure_type": "",
            "structural_system": "",
            "storey_band": "",
            "provenance_url": "https://example.bim.or.kr/d.ifc",
            "download_url": "",
            "promotion_target": "public_structural_preview",
            "promotion_flow": "derived_structural_preview_candidate",
            "promotion_status": "pending_solver_ready_reconstruction",
            "promotion_blocker": "curated_local_ifc_reference_required",
            "native_writeback_candidate": False,
            "curated_local_ifc_required": True,
            "curated_local_ifc_status": "required_missing",
            "curated_local_ifc_reference": "",
            "structural_preview_case_id": "ifc_public_award_structure__structural_preview_candidate",
            "structural_preview_writeback_case_id": "ifc_public_award_structure__structural_preview_candidate__identity_writeback",
            "derived_role": "native_source_korean_structural_preview_candidate",
            "derived_writeback_role": "native_writeback_korean_structural_preview_candidate",
            "native_writeback_ready": False,
            "solver_ready_reconstruction_artifact_json": "",
            "solver_ready_reconstruction_artifact_markdown": "",
            "solver_ready_reconstruction_summary_line": "",
        }
    ]
    assert payload["inputs"]["korean_source_catalog"] == str(korean_catalog)


def test_generate_midas_native_corpus_manifest_uses_prepared_korean_solver_ready_reconstruction(
    tmp_path: Path,
) -> None:
    quality_catalog = tmp_path / "quality_catalog.json"
    quality_report = tmp_path / "quality_report.json"
    public_catalog = tmp_path / "public_catalog.json"
    public_report = tmp_path / "public_report.json"
    korean_catalog = tmp_path / "korean_source_catalog.json"
    reconstruction_report = tmp_path / "korean_solver_ready_reconstruction_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_mgt = tmp_path / "source.mgt"
    source_conversion = tmp_path / "source_conversion_report.json"
    writeback_mgt = tmp_path / "writeback.mgt"
    writeback_roundtrip = tmp_path / "writeback_roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    fixture_dir = tmp_path / "fixture"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"
    public_parsed_json = tmp_path / "public_native_case.json"
    public_conversion_report = tmp_path / "public_native_case_report.json"

    source_mgt.write_text("*VERSION\n", encoding="utf-8")
    writeback_mgt.write_text("*VERSION\n", encoding="utf-8")
    public_parsed_json.write_text("{}", encoding="utf-8")
    _write_json(public_conversion_report, {"contract_pass": True})
    _write_json(quality_catalog, {"sources": []})
    _write_json(quality_report, {"contract_pass": True, "accepted": [], "summary": {}})
    _write_json(public_catalog, {"sources": [{"source_id": "public_native_case", "source_class": "gtc_public_native"}]})
    _write_json(
        public_report,
        {
            "contract_pass": True,
            "accepted": [
                {
                    "source_id": "public_native_case",
                    "source_class": "gtc_public_native",
                    "accepted": True,
                    "artifacts": {
                        "mgt": str(source_mgt),
                        "parsed_json": str(public_parsed_json),
                        "conversion_report": str(public_conversion_report),
                    },
                    "metrics": {"node_count": 1, "element_count": 1},
                    "checks": {"parseable": True, "quality_pass": True, "download_ok": True},
                }
            ],
            "records": [],
            "summary": {"accepted_parseable_count": 1, "unknown_row_total": 0},
        },
    )
    _write_json(
        korean_catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "provenance_url": "https://example.bim.or.kr/d.ifc",
                    "exact_topology_candidate": True,
                }
            ]
        },
    )
    _write_json(
        reconstruction_report,
        {
            "summary": {"candidate_count": 1, "prepared_count": 1},
            "rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "artifact_json": str(tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.json"),
                    "artifact_markdown": str(tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.md"),
                    "summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure",
                    "contract_pass": True,
                    "reconstruction_ready": True,
                }
            ],
        },
    )
    source_sha = _sha256(source_mgt)
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {"summary": {"audit_review_queue_pending_count": 0, "direct_patch_change_count": 0}},
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(reconstruction_report),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(fixture_dir),
            "--generated-root",
            str(generated_root),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert out.exists(), proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    row = payload["korean_exact_topology_candidate_rows"][0]
    assert row["status"] == "pending_structural_preview_materialization"
    assert row["blocker"] == "korean_structural_preview_materialization_pending"
    assert row["solver_ready_reconstruction_artifact_json"].endswith(
        "ifc_public_award_structure.solver_ready_reconstruction.json"
    )
    derived = payload["korean_structural_preview_candidate_rows"][0]
    assert derived["promotion_status"] == "pending_structural_preview_materialization"
    assert derived["solver_ready_reconstruction_summary_line"].startswith(
        "Korean IFC solver-ready reconstruction artifact: PASS"
    )


def test_generate_midas_native_corpus_manifest_infers_new_public_structure_types() -> None:
    assert (
        _infer_structure_type(
            source_id="gtc_public_bridge_bearing_c04",
            source_family="gtc_public_bridge_bearing",
        )
        == "bearing"
    )
    assert (
        _infer_structure_type(
            source_id="gtc_public_bridge_section_e1_03",
            source_family="gtc_public_bridge_section",
        )
        == "bridge_section"
    )
    assert (
        _infer_structure_type(
            source_id="midas_support_beam_archive",
            source_family="midas_support_attachment",
        )
        == "beam"
    )
    assert (
        _infer_structure_type(
            source_id="midas_support_multifamily_building_archive",
            source_family="midas_support_attachment",
        )
        == "building"
    )


def test_generate_midas_native_corpus_manifest_promotes_korean_exact_topology_when_reconstruction_artifact_is_materialized(
    tmp_path: Path,
) -> None:
    source_mgt = tmp_path / "model.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    writeback_mgt = tmp_path / "model.optimized.mgt"
    writeback_mgt.write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")

    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_conversion = tmp_path / "midas_mgt_conversion_report.json"
    writeback_roundtrip = tmp_path / "roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    public_catalog = tmp_path / "missing_public_native_mgt_source_catalog.json"
    public_report = tmp_path / "missing_public_native_corpus_report.json"
    korean_catalog = tmp_path / "korean_source_catalog.json"
    reconstruction_report = tmp_path / "korean_solver_ready_reconstruction_report.json"
    artifact_root = tmp_path / "solver_ready_reconstruction"
    fixture_dir = tmp_path / "empty_fixtures"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"

    source_sha = _sha256(source_mgt)
    _write_json(
        quality_catalog,
        {
            "sources": [
                {"source_id": "native_case", "source_family": "github_real_export", "source_class": "mgt_text"},
                {"source_id": "archive_case", "source_family": "midas_archive_bundle", "source_class": "midas_archive"},
            ]
        },
    )
    _write_json(
        quality_report,
        {
            "contract_pass": True,
            "summary": {
                "accepted_parseable_count": 1,
                "accepted_archive_count": 1,
                "recognized_archive_member_total": 1,
            },
            "accepted": [
                {
                    "source_id": "native_case",
                    "source_class": "mgt_text",
                    "sha256": source_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"mgt": str(source_mgt)},
                    "metrics": {"node_count": 1, "element_count": 0},
                },
                {
                    "source_id": "archive_case",
                    "source_class": "midas_archive",
                    "sha256": "archive",
                    "parse_ok": False,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"archive_members": ["A.mgt"]},
                    "metrics": {"recognized_midas_member_count": 1},
                },
            ],
        },
    )
    _write_json(
        korean_catalog,
        {
            "schema_version": "korean_source_catalog.v1",
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "exact_topology_candidate": True,
                    "native_writeback_candidate": False,
                    "provenance_url": "https://example.bim.or.kr/d.ifc",
                }
            ],
        },
    )
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {
            "summary": {
                "audit_review_queue_pending_count": 0,
                "direct_patch_change_count": 0,
                "direct_patch_action_family_counts": {},
                "loadcomb_roundtrip_pass": True,
                "output_mgt_exists": True,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_combo_count": 0,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})
    artifact_json = (
        artifact_root
        / "ifc_public_award_structure"
        / "ifc_public_award_structure.solver_ready_reconstruction_artifact.json"
    )
    artifact_md = (
        artifact_root
        / "ifc_public_award_structure"
        / "ifc_public_award_structure.solver_ready_reconstruction_artifact.md"
    )
    _write_json(
        artifact_json,
        {
            "schema_version": "1.0",
            "source_id": "ifc_public_award_structure",
            "contract_pass": True,
            "summary": {"reconstruction_ready": True},
            "metrics": {
                "ifc_beam_count": 2,
                "ifc_column_count": 1,
                "ifc_slab_count": 0,
                "ifc_wall_count": 0,
                "ifc_plate_count": 0,
                "ifc_member_count": 0,
                "ifc_footing_count": 0,
                "ifc_storey_count": 2,
                "ifc_structural_entity_total": 3,
            },
        },
    )
    artifact_md.parent.mkdir(parents=True, exist_ok=True)
    artifact_md.write_text("# ifc_public_award_structure\n", encoding="utf-8")
    _write_json(
        reconstruction_report,
        {
            "summary": {"candidate_count": 1, "prepared_count": 1},
            "rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "artifact_json": str(artifact_json),
                    "artifact_markdown": str(artifact_md),
                    "contract_pass": True,
                    "reconstruction_ready": True,
                    "summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=2 | structural_entities=3",
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(reconstruction_report),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(fixture_dir),
            "--generated-root",
            str(generated_root),
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
    assert payload["summary"]["korean_solver_ready_reconstruction_prepared_count"] == 1
    assert payload["summary"]["korean_solver_ready_reconstruction_candidate_count"] == 1
    assert payload["summary"]["korean_source_catalog_exact_topology_candidate_count"] == 1
    assert payload["summary"]["korean_source_catalog_exact_topology_candidate_pending_count"] == 0
    assert payload["summary"]["public_archive_structural_preview_text_case_count"] == 1
    assert payload["summary"]["public_archive_structural_preview_writeback_ready_count"] == 1
    assert payload["summary"]["public_native_writeback_ready_count"] == 1
    assert payload["summary"]["public_source_writeback_ready_count"] == 2
    assert payload["summary"]["native_writeback_ready_count"] == 2
    assert payload["korean_exact_topology_candidate_rows"] == [
        {
            "source_id": "ifc_public_award_structure",
            "title": "IFC award structure",
            "source_class": "ifc_public",
            "origin_type": "bim_award_archive",
            "origin_org": "",
            "format": "ifc",
            "content_kind": "ifc_structural_subset",
            "structure_type": "",
            "structural_system": "",
            "storey_band": "",
            "ingest_status": "",
            "provenance_url": "https://example.bim.or.kr/d.ifc",
            "download_url": "",
            "native_writeback_candidate": False,
            "exact_topology_candidate": True,
            "curated_local_ifc_required": False,
            "curated_local_ifc_status": "",
            "curated_local_ifc_reference": "",
            "promotion_target": "public_structural_preview",
            "status": "public_structural_preview_ready",
            "blocker": "",
            "solver_ready_reconstruction_artifact_json": str(artifact_json),
            "solver_ready_reconstruction_artifact_markdown": str(artifact_md),
            "solver_ready_reconstruction_summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=2 | structural_entities=3",
        }
    ]
    assert payload["korean_structural_preview_candidate_rows"] == [
        {
            "source_id": "ifc_public_award_structure",
            "title": "IFC award structure",
            "candidate_origin": "korean_source_catalog",
            "source_class": "ifc_public",
            "format": "ifc",
            "content_kind": "ifc_structural_subset",
            "structure_type": "",
            "structural_system": "",
            "storey_band": "",
            "provenance_url": "https://example.bim.or.kr/d.ifc",
            "download_url": "",
            "promotion_target": "public_structural_preview",
            "promotion_flow": "derived_structural_preview_candidate",
            "promotion_status": "public_structural_preview_ready",
            "promotion_blocker": "",
            "native_writeback_candidate": False,
            "curated_local_ifc_required": False,
            "curated_local_ifc_status": "",
            "curated_local_ifc_reference": "",
            "structural_preview_case_id": "ifc_public_award_structure__structural_preview_candidate",
            "structural_preview_writeback_case_id": "ifc_public_award_structure__structural_preview_candidate__identity_writeback",
            "derived_role": "native_source_korean_structural_preview_candidate",
            "derived_writeback_role": "native_writeback_korean_structural_preview_candidate",
            "native_writeback_ready": True,
            "solver_ready_reconstruction_artifact_json": str(artifact_json),
            "solver_ready_reconstruction_artifact_markdown": str(artifact_md),
            "solver_ready_reconstruction_summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=2 | structural_entities=3",
        }
    ]
    assert payload["summary"]["korean_structural_preview_candidate_count"] == 1
    assert payload["summary"]["korean_source_catalog_exact_topology_candidate_pending_count"] == 0
    assert any(
        case["case_id"] == "ifc_public_award_structure__structural_preview_candidate"
        and case["role"] == "native_source_public_archive_structural_preview"
        for case in payload["cases"]
    )
    assert any(
        case["case_id"] == "ifc_public_award_structure__structural_preview_candidate__identity_writeback"
        and case["role"] == "native_writeback_public_archive_structural_preview_derived"
        and case["native_writeback_ready"] is True
        for case in payload["cases"]
    )
    assert (
        _infer_structure_type(
            source_id="midas_support_neighborhood_facility_archive",
            source_family="midas_support_attachment",
        )
        == "building"
    )
    assert (
        _infer_structure_type(
            source_id="midas_support_stair_archive",
            source_family="midas_support_attachment",
        )
        == "stair"
    )
    assert (
        _infer_structure_type(
            source_id="midas_support_ramp_archive",
            source_family="midas_support_attachment",
        )
        == "ramp"
    )
    assert _preview_structure_type("midas_support_beam_archive", "archive_reference") == "beam"
    assert _preview_structure_type("midas_support_neighborhood_facility_archive", "archive_reference") == "building"
    assert _preview_structure_type("midas_support_stair_archive", "archive_reference") == "stair"
    assert _preview_structure_type("midas_support_ramp_archive", "archive_reference") == "ramp"


def test_generate_midas_native_corpus_manifest_uses_prepared_korean_reconstruction(tmp_path: Path) -> None:
    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    public_catalog = tmp_path / "public_native_mgt_source_catalog.json"
    public_report = tmp_path / "public_native_corpus_report.json"
    korean_catalog = tmp_path / "korean_source_catalog.json"
    korean_reconstruction = tmp_path / "korean_solver_ready_reconstruction_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_mgt = tmp_path / "source.mgt"
    source_conversion = tmp_path / "source_conversion.json"
    writeback_mgt = tmp_path / "writeback.mgt"
    writeback_roundtrip = tmp_path / "writeback_roundtrip.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip.json"
    out = tmp_path / "midas_native_corpus_manifest.json"

    source_mgt.write_text("*UNIT\n", encoding="utf-8")
    writeback_mgt.write_text("*UNIT\n", encoding="utf-8")
    for path, payload in (
        (quality_catalog, {"sources": [{"source_id": "q1", "source_family": "quality"}]}),
        (quality_report, {"contract_pass": True, "summary": {"accepted_source_count": 1}, "accepted": []}),
        (public_catalog, {"sources": []}),
        (public_report, {"contract_pass": True, "summary": {"accepted_source_count": 0}, "accepted": [], "records": []}),
        (
            korean_catalog,
            {
                "source_records": [
                    {
                        "source_id": "ifc_public_award_structure",
                        "title": "IFC award structure",
                        "source_class": "ifc_public",
                        "origin_type": "bim_award_archive",
                        "origin_org": "",
                        "format": "ifc",
                        "content_kind": "ifc_structural_subset",
                        "structure_type": "",
                        "structural_system": "",
                        "storey_band": "",
                        "ingest_status": "",
                        "provenance_url": "https://example.bim.or.kr/d.ifc",
                        "download_url": "",
                        "native_writeback_candidate": False,
                        "exact_topology_candidate": True,
                    }
                ]
            },
        ),
        (
            korean_reconstruction,
            {
                "summary": {"candidate_count": 1, "prepared_count": 1},
                "rows": [
                    {
                        "source_id": "ifc_public_award_structure",
                        "artifact_json": str(tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.json"),
                        "artifact_markdown": str(tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.md"),
                        "contract_pass": True,
                        "reconstruction_ready": True,
                        "summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=1 | structural_entities=3",
                    }
                ],
            },
        ),
        (source_manifest, {"entries": []}),
        (source_conversion, {"contract_pass": True}),
        (writeback_roundtrip, {"contract_pass": True}),
        (export_report, {"contract_pass": True, "summary": {"audit_review_queue_pending_count": 0, "direct_patch_change_count": 0}}),
        (patch_manifest, {"contract_pass": True}),
        (loadcomb_roundtrip, {"contract_pass": True}),
    ):
        _write_json(path, payload)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(korean_reconstruction),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(tmp_path),
            "--generated-root",
            str(tmp_path / "generated"),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode in {0, 1}, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["korean_solver_ready_reconstruction_candidate_count"] == 1
    assert payload["summary"]["korean_solver_ready_reconstruction_prepared_count"] == 1
    assert payload["korean_exact_topology_candidate_rows"][0]["status"] == "pending_structural_preview_materialization"
    assert payload["korean_exact_topology_candidate_rows"][0]["blocker"] == "korean_structural_preview_materialization_pending"
    assert payload["korean_exact_topology_candidate_rows"][0]["solver_ready_reconstruction_artifact_json"].endswith(
        "ifc_public_award_structure.solver_ready_reconstruction.json"
    )


def test_generate_midas_native_corpus_manifest_materializes_korean_public_structural_preview(
    tmp_path: Path,
) -> None:
    source_mgt = tmp_path / "model.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    writeback_mgt = tmp_path / "model.optimized.mgt"
    writeback_mgt.write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")

    quality_catalog = tmp_path / "quality_mgt_source_catalog.json"
    quality_report = tmp_path / "quality_corpus_report.json"
    source_manifest = tmp_path / "source_manifest.json"
    source_conversion = tmp_path / "midas_mgt_conversion_report.json"
    writeback_roundtrip = tmp_path / "roundtrip_report.json"
    export_report = tmp_path / "export_report.json"
    patch_manifest = tmp_path / "patch_manifest.json"
    loadcomb_roundtrip = tmp_path / "loadcomb_roundtrip_report.json"
    public_catalog = tmp_path / "missing_public_native_mgt_source_catalog.json"
    public_report = tmp_path / "missing_public_native_corpus_report.json"
    korean_catalog = tmp_path / "korean_source_catalog.json"
    korean_reconstruction = tmp_path / "korean_solver_ready_reconstruction_report.json"
    generated_root = tmp_path / "generated"
    out = tmp_path / "midas_native_corpus_manifest.json"
    local_ifc = tmp_path / "award.ifc"
    local_ifc.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "ENDSEC;",
                "DATA;",
                "#1=IFCBUILDINGSTOREY('a',$,'L1',$,$,$,$,$);",
                "#2=IFCBUILDINGSTOREY('b',$,'L2',$,$,$,$,$);",
                "#3=IFCCOLUMN('c',$,'C1',$,$,$,$);",
                "#4=IFCBEAM('d',$,'B1',$,$,$,$);",
                "#5=IFCSLAB('e',$,'S1',$,$,$,$,.FLOOR.);",
                "ENDSEC;",
                "END-ISO-10303-21;",
            ]
        ),
        encoding="utf-8",
    )
    reconstruction_artifact_json = tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.json"
    reconstruction_artifact_md = tmp_path / "ifc_public_award_structure.solver_ready_reconstruction.md"
    reconstruction_artifact_md.write_text("# reconstruction\n", encoding="utf-8")
    _write_json(
        reconstruction_artifact_json,
        {
            "schema_version": "1.0",
            "run_id": "phase1-korean-ifc-solver-ready-reconstruction",
            "generated_at": "2026-04-08T00:00:00Z",
            "source_id": "ifc_public_award_structure",
            "local_ifc_path": str(local_ifc),
            "metrics": {
                "ifc_beam_count": 1,
                "ifc_column_count": 1,
                "ifc_slab_count": 1,
                "ifc_wall_count": 0,
                "ifc_plate_count": 0,
                "ifc_member_count": 0,
                "ifc_footing_count": 0,
                "ifc_storey_count": 2,
                "ifc_structural_entity_total": 3,
            },
            "summary": {"reconstruction_ready": True},
            "summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=2 | structural_entities=3",
            "contract_pass": True,
        },
    )

    source_sha = _sha256(source_mgt)
    _write_json(
        quality_catalog,
        {
            "sources": [
                {"source_id": "native_case", "source_family": "github_real_export", "source_class": "mgt_text"},
                {"source_id": "archive_case", "source_family": "midas_archive_bundle", "source_class": "midas_archive"},
            ]
        },
    )
    _write_json(
        quality_report,
        {
            "contract_pass": True,
            "summary": {
                "accepted_parseable_count": 1,
                "accepted_archive_count": 1,
                "recognized_archive_member_total": 1,
            },
            "accepted": [
                {
                    "source_id": "native_case",
                    "source_class": "mgt_text",
                    "sha256": source_sha,
                    "parse_ok": True,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"mgt": str(source_mgt)},
                    "metrics": {"node_count": 1, "element_count": 0},
                },
                {
                    "source_id": "archive_case",
                    "source_class": "midas_archive",
                    "sha256": "archive",
                    "parse_ok": False,
                    "quality_pass": True,
                    "download_ok": True,
                    "artifacts": {"archive_members": ["A.mgt"]},
                    "metrics": {"recognized_midas_member_count": 1},
                },
            ],
        },
    )
    _write_json(public_catalog, {"sources": []})
    _write_json(public_report, {"contract_pass": True, "accepted": [], "records": [], "summary": {}})
    _write_json(
        korean_catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "IFC award structure",
                    "source_class": "ifc_public",
                    "origin_type": "bim_award_archive",
                    "format": "ifc",
                    "content_kind": "ifc_structural_subset",
                    "structure_type": "building",
                    "structural_system": "steel_frame",
                    "storey_band": "mid_rise",
                    "provenance_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                    "download_url": "https://example.buildingsmart.or.kr/award-structure.ifc",
                    "exact_topology_candidate": True,
                    "curated_local_ifc_required": True,
                    "curated_local_ifc_status": "attached",
                    "curated_local_ifc_reference": str(local_ifc),
                }
            ]
        },
    )
    _write_json(
        korean_reconstruction,
        {
            "summary": {"candidate_count": 1, "prepared_count": 1},
            "rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "artifact_json": str(reconstruction_artifact_json),
                    "artifact_markdown": str(reconstruction_artifact_md),
                    "contract_pass": True,
                    "reconstruction_ready": True,
                    "summary_line": "Korean IFC solver-ready reconstruction artifact: PASS | source=ifc_public_award_structure | storeys=2 | structural_entities=3",
                }
            ],
        },
    )
    _write_json(source_manifest, {"out": str(source_mgt), "sha256": source_sha})
    _write_json(source_conversion, {"metrics": {}, "contract_pass": True})
    _write_json(writeback_roundtrip, {"metrics": {}, "contract_pass": True})
    _write_json(
        export_report,
        {
            "summary": {
                "audit_review_queue_pending_count": 0,
                "direct_patch_change_count": 0,
                "direct_patch_action_family_counts": {},
                "loadcomb_roundtrip_pass": True,
                "output_mgt_exists": True,
                "instruction_sidecar_audit_only_change_count": 0,
                "loadcomb_combo_count": 0,
            }
        },
    )
    _write_json(patch_manifest, {"changes": []})
    _write_json(loadcomb_roundtrip, {"pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--quality-catalog",
            str(quality_catalog),
            "--quality-corpus-report",
            str(quality_report),
            "--public-native-catalog",
            str(public_catalog),
            "--public-native-corpus-report",
            str(public_report),
            "--korean-source-catalog",
            str(korean_catalog),
            "--korean-solver-ready-reconstruction-report",
            str(korean_reconstruction),
            "--source-manifest",
            str(source_manifest),
            "--source-mgt",
            str(source_mgt),
            "--source-conversion-report",
            str(source_conversion),
            "--writeback-mgt",
            str(writeback_mgt),
            "--writeback-roundtrip-report",
            str(writeback_roundtrip),
            "--export-report",
            str(export_report),
            "--patch-manifest",
            str(patch_manifest),
            "--loadcomb-roundtrip-report",
            str(loadcomb_roundtrip),
            "--fixture-dir",
            str(tmp_path / "fixtures"),
            "--generated-root",
            str(generated_root),
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
    assert payload["summary"]["public_archive_structural_preview_text_case_count"] == 1
    assert payload["summary"]["public_archive_structural_preview_writeback_ready_count"] == 1
    assert payload["summary"]["public_source_writeback_ready_count"] == 2
    assert payload["korean_exact_topology_candidate_rows"][0]["status"] == "public_structural_preview_ready"
    assert payload["korean_exact_topology_candidate_rows"][0]["blocker"] == ""
    assert payload["korean_structural_preview_candidate_rows"][0]["promotion_status"] == "public_structural_preview_ready"
    assert payload["korean_structural_preview_candidate_rows"][0]["promotion_blocker"] == ""
    assert payload["korean_structural_preview_candidate_rows"][0]["native_writeback_ready"] is True
    source_case = next(
        row
        for row in payload["cases"]
        if row["role"] == "native_source_public_archive_structural_preview"
    )
    writeback_case = next(
        row
        for row in payload["cases"]
        if row["role"] == "native_writeback_public_archive_structural_preview_derived"
    )
    assert source_case["source_id"] == "ifc_public_award_structure"
    assert source_case["case_id"] == "ifc_public_award_structure__structural_preview_candidate"
    assert source_case["checks"]["exact_topology_candidate"] is True
    assert writeback_case["case_id"] == "ifc_public_award_structure__structural_preview_candidate__identity_writeback"
    assert writeback_case["writeback_mode"] == "public_archive_structural_preview_identity_baseline"
    assert writeback_case["native_writeback_ready"] is True


def test_append_public_bridge_baseline_rows_adds_beam_family(monkeypatch, tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridged"
    beam_dir = bridge_root / "midas_support_beam_archive"
    beam_dir.mkdir(parents=True)
    (beam_dir / "model.json").write_text(
        json.dumps(
            {
                "model": {
                    "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}, {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0}],
                    "elements": [{"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2]}],
                    "materials": [],
                    "sections": [],
                },
                "topology_metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    bridge_report = {
        "summary": {
            "viewer_ready": True,
            "family_assumption": "beam",
            "node_count": 2,
            "element_count": 1,
            "member_id_count": 1,
        }
    }
    (beam_dir / "bridge_report.json").write_text(json.dumps(bridge_report, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "implementation.phase1.generate_midas_native_corpus_manifest.MIDAS_QUALITY_BRIDGED_ROOT",
        bridge_root,
    )

    assert _bridge_baseline_structure_type("midas_support_beam_archive", "bridge", bridge_report) == "beam"


def test_append_public_bridge_baseline_rows_adds_public_bridge_cases(monkeypatch, tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridged"
    source_id = "midas_support_beam_archive"
    bridge_dir = bridge_root / source_id
    generated_root = tmp_path / "generated"
    bridge_case_id = f"{source_id}__bridge_native"
    generated_case_dir = generated_root / "midas_support_beam_archive_bridge_native"

    bridge_dir.mkdir(parents=True)
    generated_case_dir.mkdir(parents=True)
    (bridge_dir / "model.json").write_text(
        json.dumps(
            {
                "model": {
                    "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}, {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0}],
                    "elements": [{"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2]}],
                    "materials": [],
                    "sections": [],
                },
                "topology_metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (bridge_dir / "bridge_report.json").write_text(
        json.dumps(
            {
                "summary": {
                    "viewer_ready": True,
                    "family_assumption": "beam",
                    "node_count": 2,
                    "element_count": 1,
                    "member_id_count": 1,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (generated_case_dir / f"{bridge_case_id}.mgt").write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")
    (generated_case_dir / f"{bridge_case_id}.identity_writeback.mgt").write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")
    for filename in [
        "source_conversion_report.json",
        "writeback_roundtrip_report.json",
        "fixture_export_report.json",
        "fixture_patch_manifest.json",
        "fixture_loadcomb_roundtrip_report.json",
    ]:
        (generated_case_dir / filename).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "implementation.phase1.generate_midas_native_corpus_manifest.MIDAS_QUALITY_BRIDGED_ROOT",
        bridge_root,
    )

    cases: list[dict[str, object]] = []
    archive_cases = [
        {
            "source_id": source_id,
            "source_family": "midas_support_attachment",
            "structure_type": "building",
            "checks": {"quality_pass": True, "download_ok": True},
            "artifacts": {"archive_members": ["A.mgt", "B.mgt"]},
            "url": "https://example.com/archive",
        }
    ]

    _append_public_bridge_baseline_rows(
        cases=cases,
        archive_source_cases=archive_cases,
        generated_root=generated_root,
    )

    assert len(cases) == 2
    source_case, writeback_case = cases
    assert source_case["case_id"] == bridge_case_id
    assert source_case["role"] == "native_source_public_bridge"
    assert source_case["structure_type"] == "beam"
    assert source_case["native_writeback_ready"] is True
    assert source_case["writeback_case_id"] == f"{bridge_case_id}__identity_writeback"
    assert source_case["artifacts"]["source"]["exists"] is True
    assert source_case["artifacts"]["bridge_model_json"]["exists"] is True
    assert source_case["artifacts"]["bridge_report"]["exists"] is True
    assert source_case["artifacts"]["archive_members"] == ["A.mgt", "B.mgt"]
    assert writeback_case["case_id"] == f"{bridge_case_id}__identity_writeback"
    assert writeback_case["role"] == "native_writeback_public_bridge_derived"
    assert writeback_case["writeback_mode"] == "public_bridge_identity_baseline"
    assert writeback_case["native_writeback_ready"] is True
    assert writeback_case["checks"]["bridge_identity_mode"] is True
    assert writeback_case["artifacts"]["writeback_mgt"]["exists"] is True
    assert writeback_case["artifacts"]["bridge_model_json"]["exists"] is True
    assert writeback_case["artifacts"]["bridge_report"]["exists"] is True

    cases: list[dict] = []
    _append_public_bridge_baseline_rows(
        cases=cases,
        archive_source_cases=[
            {
                "source_id": "midas_support_beam_archive",
                "source_family": "midas_support_attachment",
                "structure_type": "beam",
                "url": "https://example.invalid/beam.zip",
                "artifacts": {"archive_members": ["FCM Bridge.mcb"]},
                "checks": {"quality_pass": True, "download_ok": True},
            }
        ],
        generated_root=tmp_path / "generated",
    )

    assert [row["role"] for row in cases] == [
        "native_source_public_bridge",
        "native_writeback_public_bridge_derived",
    ]
    assert cases[0]["structure_type"] == "beam"
    assert cases[0]["writeback_case_id"] == "midas_support_beam_archive__bridge_native__identity_writeback"
    assert cases[1]["writeback_mode"] == "public_bridge_identity_baseline"


def test_append_public_archive_structural_preview_rows_adds_exact_topology_cases(monkeypatch, tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridged"
    source_id = "midas_support_ramp_archive"
    preview_dir = bridge_root / f"{source_id}_decoded_preview"
    generated_root = tmp_path / "generated"
    structural_case_id = f"{source_id}__structural_preview_native"
    generated_case_dir = generated_root / "midas_support_ramp_archive_structural_preview_native"

    preview_dir.mkdir(parents=True)
    generated_case_dir.mkdir(parents=True)
    (preview_dir / "model.json").write_text(
        json.dumps(
            {
                "model": {
                    "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}, {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0}],
                    "elements": [{"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2]}],
                    "materials": [],
                    "sections": [],
                },
                "topology_metrics": {"node_count": 2, "element_count": 1, "beam_element_count": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (preview_dir / "bridge_report.json").write_text(
        json.dumps(
            {
                "summary": {
                    "viewer_ready": True,
                    "exact_topology_candidate": True,
                    "preview_surface_status_label": "exact recovered topology-derived 3d candidate",
                    "node_count": 2,
                    "element_count": 1,
                    "member_id_count": 1,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (generated_case_dir / f"{structural_case_id}.mgt").write_text("*NODE\n1,0,0,0\n*ENDDATA\n", encoding="utf-8")
    (generated_case_dir / f"{structural_case_id}.identity_writeback.mgt").write_text(
        "*NODE\n1,0,0,0\n*ENDDATA\n",
        encoding="utf-8",
    )
    for filename in [
        "source_conversion_report.json",
        "writeback_roundtrip_report.json",
        "fixture_export_report.json",
        "fixture_patch_manifest.json",
        "fixture_loadcomb_roundtrip_report.json",
    ]:
        (generated_case_dir / filename).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "implementation.phase1.generate_midas_native_corpus_manifest.MIDAS_QUALITY_BRIDGED_ROOT",
        bridge_root,
    )

    cases: list[dict[str, object]] = []
    _append_public_archive_structural_preview_rows(
        cases=cases,
        archive_source_cases=[
            {
                "source_id": source_id,
                "source_family": "midas_support_attachment",
                "structure_type": "ramp",
                "url": "https://example.com/ramp.zip",
                "artifacts": {"archive_members": ["RampModel.mcb"]},
                "checks": {"quality_pass": True, "download_ok": True},
            }
        ],
        generated_root=generated_root,
    )

    assert [row["role"] for row in cases] == [
        "native_source_public_archive_structural_preview",
        "native_writeback_public_archive_structural_preview_derived",
    ]
    assert cases[0]["structure_type"] == "ramp"
    assert cases[1]["writeback_mode"] == "public_archive_structural_preview_identity_baseline"
