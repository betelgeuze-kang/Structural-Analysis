from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module(module_relative_path: str, module_name: str):
    module_path = Path(__file__).resolve().parents[1] / module_relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_expert_review_metadata_fixture(tmp_path: Path) -> dict[str, Path | dict]:
    review_ui = _load_module(
        "implementation/phase1/generate_optimized_drawing_review_ui.py",
        "optimized_drawing_review_ui_module_for_pdf",
    )

    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    out_expert_metadata_json = tmp_path / "optimized_drawing_expert_review.metadata.json"

    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "fixture_pdf_case",
                "case_title": "Fixture PDF Case",
                "case_note": "한글 deterministic expert review export",
                "status_label": "baseline + ai compare",
                "expert_review_metadata": {
                    "project_name": "한글 PDF 타워",
                    "project_number": "PDF-2026-01",
                    "authority_name": "서울 구조 심의위원회",
                    "package_id": "PDF-PKG-01",
                    "revision_code": "REV-PDF",
                    "revision_status": "Issued for expert validation",
                },
            },
            "baseline_structure": {
                "total_element_count": 4,
                "plan_xy_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#eee'/></svg>",
                "elevation_xz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ddd'/></svg>",
                "isometric_xyz_svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='#ccc'/></svg>",
            },
            "member_overlay": {
                "changed_member_count": 2,
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
                        "before_after_snapshot_note": "section A -> B",
                    },
                    {
                        "member_id": "C-201",
                        "member_type": "column",
                        "story_band_label": "S04",
                        "zone_label": "core",
                        "action_name_label": "column trim",
                        "cost_delta": -8.3,
                        "constructability_delta": -0.09,
                        "before_after_snapshot_note": "column C1 -> C2",
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
                    }
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
                        "changed_group_count": 2,
                        "cost_proxy_delta_sum": -20.8,
                        "constructability_delta_sum": -0.24,
                        "max_dcr_after_max": 0.92,
                    }
                ],
                "story_band_rows": [
                    {
                        "story_band": "S05",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 2,
                        "cost_proxy_delta_sum": -20.8,
                        "constructability_delta_sum": -0.24,
                        "max_dcr_after_max": 0.92,
                    }
                ],
                "zone_rows": [],
            },
            "artifact_links": {
                "viewer_html": "structural_optimization_viewer.html",
                "project_registry_report": "release/project_registry.json",
                "project_package_zip": "release/project_package.zip",
                "project_registry_signature": "release/signing/project_registry.signature.b64",
                "external_benchmark_batch_job_report_json": "release/external_benchmark_kickoff/external_benchmark_batch_job_report.json",
            },
        },
    )

    summary = review_ui.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_expert_review_issue_metadata.json",
        out_expert_metadata_json=out_expert_metadata_json,
    )

    assert summary["output_expert_metadata_json"] == str(out_expert_metadata_json)
    assert out_expert_metadata_json.exists()
    return {
        "viewer_json": viewer_json,
        "out_html": out_html,
        "out_summary": out_summary,
        "out_expert_metadata_json": out_expert_metadata_json,
        "summary": summary,
    }


def test_export_expert_review_pdf_is_deterministic(tmp_path: Path) -> None:
    exporter = _load_module(
        "implementation/phase1/export_optimized_drawing_expert_review_pdf.py",
        "optimized_drawing_expert_review_pdf_exporter",
    )
    fixture = _build_expert_review_metadata_fixture(tmp_path)
    out_expert_metadata_json = fixture["out_expert_metadata_json"]
    assert isinstance(out_expert_metadata_json, Path)
    out_pdf_a = tmp_path / "optimized_drawing_expert_review_a.pdf"
    out_pdf_b = tmp_path / "optimized_drawing_expert_review_b.pdf"

    export_a = exporter.export_expert_review_pdf(
        expert_review_metadata_json=out_expert_metadata_json,
        out_pdf=out_pdf_a,
    )
    export_b = exporter.export_expert_review_pdf(
        expert_review_metadata_json=out_expert_metadata_json,
        out_pdf=out_pdf_b,
    )

    assert export_a["out_pdf"] == str(out_pdf_a)
    assert export_b["out_pdf"] == str(out_pdf_b)
    assert out_pdf_a.exists()
    assert out_pdf_b.exists()
    assert out_pdf_a.stat().st_size > 2000
    assert out_pdf_a.read_bytes() == out_pdf_b.read_bytes()
    from pypdf import PdfReader

    extracted_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(out_pdf_a)).pages)
    assert "한글 PDF 타워" in extracted_text
    assert "서울 구조 심의위원회" in extracted_text
    assert "project_registry.json" in extracted_text
    assert "external_benchmark_batch_job_report.json" in extracted_text


def test_export_expert_review_pdf_batch_generates_templates_and_receipt(tmp_path: Path) -> None:
    exporter = _load_module(
        "implementation/phase1/export_optimized_drawing_expert_review_pdf.py",
        "optimized_drawing_expert_review_pdf_exporter_batch",
    )
    fixture = _build_expert_review_metadata_fixture(tmp_path)
    out_expert_metadata_json = fixture["out_expert_metadata_json"]
    assert isinstance(out_expert_metadata_json, Path)
    batch_dir = tmp_path / "expert_pdf_batch"

    batch_result = exporter.export_expert_review_pdf_batch(
        expert_review_metadata_json=out_expert_metadata_json,
        out_dir=batch_dir,
    )

    manifest_path = Path(str(batch_result["manifest_json"]))
    receipt_path = Path(str(batch_result["receipt_txt"]))
    assert manifest_path.exists()
    assert receipt_path.exists()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_text = receipt_path.read_text(encoding="utf-8")

    assert manifest_payload["schema_version"] == "optimized_drawing_expert_review_pdf.batch_manifest.v1"
    assert manifest_payload["template_order"] == [
        "default",
        "seoul_permit_review",
        "structural_peer_committee",
        "international_english",
    ]
    assert manifest_payload["template_count"] == 4
    assert batch_result["template_count"] == 4
    assert "optimized_drawing_expert_review_pdf_batch" in receipt_text
    assert "template_count=4" in receipt_text
    assert "default | label=Default expert review package" in receipt_text
    assert "seoul_permit_review | label=Seoul permit review package" in receipt_text
    assert "structural_peer_committee | label=Structural peer committee review package" in receipt_text
    assert "international_english | label=International English expert review package" in receipt_text

    template_rows = {row["template_name"]: row for row in manifest_payload["templates"]}
    assert set(template_rows) == {
        "default",
        "seoul_permit_review",
        "structural_peer_committee",
        "international_english",
    }

    default_pdf = batch_dir / "optimized_drawing_expert_review.default.pdf"
    seoul_pdf = batch_dir / "optimized_drawing_expert_review.seoul_permit_review.pdf"
    peer_pdf = batch_dir / "optimized_drawing_expert_review.structural_peer_committee.pdf"
    international_pdf = batch_dir / "optimized_drawing_expert_review.international_english.pdf"
    for pdf_path in [default_pdf, seoul_pdf, peer_pdf, international_pdf]:
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 2000

    assert template_rows["default"]["relative_pdf"] == "optimized_drawing_expert_review.default.pdf"
    assert template_rows["seoul_permit_review"]["authority_name"] == "Seoul Metropolitan Permit Review Office"
    assert template_rows["seoul_permit_review"]["package_purpose_label"] == "Seoul Permit Review Package"
    assert template_rows["structural_peer_committee"]["authority_name"] == "Structural Peer Committee"
    assert (
        template_rows["structural_peer_committee"]["package_purpose_label"]
        == "Structural Peer Committee Review Package"
    )
    assert template_rows["international_english"]["authority_name"] == "International Peer Review Board"
    assert (
        template_rows["international_english"]["package_purpose_label"]
        == "Design Optimization Independent Review"
    )

    from pypdf import PdfReader

    default_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(default_pdf)).pages)
    seoul_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(seoul_pdf)).pages)
    peer_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(peer_pdf)).pages)
    international_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(international_pdf)).pages)

    assert "한글 PDF 타워" in default_text
    assert "서울 구조 심의위원회" in default_text
    assert "Seoul Metropolitan Permit Review Office" in seoul_text
    assert "Seoul Permit Review Package" in seoul_text
    assert "Structural Peer Committee" in peer_text
    assert "Structural Peer Committee Review Package" in peer_text
    assert "International Peer Review Board" in international_text
    assert "Design Optimization Independent Review" in international_text

    manifest_bytes_before = manifest_path.read_bytes()
    receipt_bytes_before = receipt_path.read_bytes()
    pdf_bytes_before = {
        "default": default_pdf.read_bytes(),
        "seoul_permit_review": seoul_pdf.read_bytes(),
        "structural_peer_committee": peer_pdf.read_bytes(),
        "international_english": international_pdf.read_bytes(),
    }

    rerun_result = exporter.export_expert_review_pdf_batch(
        expert_review_metadata_json=out_expert_metadata_json,
        out_dir=batch_dir,
    )
    assert rerun_result["template_order"] == manifest_payload["template_order"]
    assert manifest_path.read_bytes() == manifest_bytes_before
    assert receipt_path.read_bytes() == receipt_bytes_before
    assert default_pdf.read_bytes() == pdf_bytes_before["default"]
    assert seoul_pdf.read_bytes() == pdf_bytes_before["seoul_permit_review"]
    assert peer_pdf.read_bytes() == pdf_bytes_before["structural_peer_committee"]
    assert international_pdf.read_bytes() == pdf_bytes_before["international_english"]
