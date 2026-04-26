from __future__ import annotations

import zipfile
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


def _build_review_metadata_fixture(tmp_path: Path) -> dict[str, Path]:
    review_ui = _load_module(
        "implementation/phase1/generate_optimized_drawing_review_ui.py",
        "optimized_drawing_review_ui_module_for_pdf_batch_zip",
    )

    viewer_json = tmp_path / "viewer.json"
    out_html = tmp_path / "optimized_drawing_review.html"
    out_expert_html = tmp_path / "optimized_drawing_expert_review.html"
    out_summary = tmp_path / "optimized_drawing_review_summary.json"
    out_expert_metadata_json = tmp_path / "optimized_drawing_expert_review.metadata.json"

    _write_json(
        viewer_json,
        {
            "case_context": {
                "case_id": "fixture_pdf_batch_case",
                "case_title": "Fixture PDF Batch Case",
                "case_note": "permit/committee batch submission fixture",
                "status_label": "baseline + ai compare",
                "expert_review_metadata": {
                    "project_name": "배치 제출 타워",
                    "project_number": "BATCH-PDF-01",
                    "authority_name": "서울 구조 심의위원회",
                    "package_id": "BATCH-PKG-01",
                    "revision_code": "REV-BATCH",
                    "revision_status": "Issued for committee submission",
                },
            },
            "baseline_structure": {
                "total_element_count": 4,
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
                        "story_band_label": "S05",
                        "zone_label": "perimeter",
                        "action_name_label": "beam section down",
                        "cost_delta": -12.5,
                        "constructability_delta": -0.15,
                        "before_after_snapshot_note": "section A -> B",
                    }
                ],
            },
            "interactive_3d": {
                "mode": "interactive_canvas_xyz_structure",
                "comparison_availability": "baseline_vs_changed",
                "baseline_segments": [],
                "after_segments": [],
            },
            "change_overview": {
                "member_type_rows": [
                    {
                        "label": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -12.5,
                        "constructability_delta_sum": -0.15,
                        "max_dcr_after_max": 0.91,
                    }
                ],
                "story_band_rows": [
                    {
                        "story_band": "S05",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "changed_group_count": 1,
                        "cost_proxy_delta_sum": -12.5,
                        "constructability_delta_sum": -0.15,
                        "max_dcr_after_max": 0.91,
                    }
                ],
                "zone_rows": [],
            },
            "artifact_links": {},
        },
    )

    review_ui.write_review_artifacts(
        viewer_json_path=viewer_json,
        out_html=out_html,
        out_expert_html=out_expert_html,
        out_summary=out_summary,
        expert_metadata_json_path=tmp_path / "missing_expert_review_issue_metadata.json",
        out_expert_metadata_json=out_expert_metadata_json,
    )
    onboarding_json = tmp_path / "project_onboarding.json"
    _write_json(
        onboarding_json,
        {
            "api_version": "expert_review_onboarding_api.v1",
            "request": {
                "request_id": "REQ-24010",
                "submitted_at": "2026-04-10T09:30:00Z",
                "submitted_by": "customer.portal@example.com",
                "submission_channel": "customer_portal",
                "template_name": "seoul_permit_review",
                "selection_reason": "Seoul permit package requested by customer.",
            },
            "project": {
                "project_name": "서울 배치 제출 타워",
                "project_number": "ONBOARD-2026-01",
                "client_name": "Example Development",
                "site_name": "Seoul Block A",
            },
            "submission": {
                "authority_name": "Seoul Metropolitan Government",
                "permit_label": "Building Permit Review",
                "committee_label": "Seoul Structural Review Committee",
                "package_purpose_label": "Permit Submission Package",
                "issue_phase_label": "Issued for permit review",
                "issue_date": "2026-04-10",
                "package_id": "ONBOARD-PKG-01",
                "revision_code": "REV-ONB",
                "revision_status": "Issued for permit review",
                "discipline_label": "Structural Optimization Review",
                "code_basis": "KDS / project criteria to be confirmed by reviewer",
            },
            "review_team": {
                "prepared_by": "AI Structural Optimization Review Tool",
                "reviewed_by": "Reviewer to sign",
                "company_name": "Example Structural Engineering",
            },
            "review_labels": {
                "checklist_head_label": "Permit checklist",
                "checklist_title": "Seoul permit issue checklist",
                "signoff_head_label": "Permit disposition",
                "signoff_title": "Seoul permit sign-off block",
                "reviewer_label": "Permit reviewer / office",
                "disposition_label": "Permit disposition",
                "comments_label": "Permit comments / conditions",
                "signature_label": "Permit signature / date",
            },
            "reviewer_guidance": {
                "review_route_note": "Machine-verifiable lines are prefilled; permit-specific remarks remain open for reviewer sign-off."
            },
            "metadata_overrides": {
                "sheet_size": "A3 landscape"
            },
        },
    )
    return {
        "viewer_json": viewer_json,
        "expert_metadata_json": out_expert_metadata_json,
        "project_onboarding_json": onboarding_json,
    }


def test_export_expert_review_pdf_batch_builds_submission_zips(tmp_path: Path) -> None:
    batch = _load_module(
        "implementation/phase1/export_optimized_drawing_expert_review_pdf_batch.py",
        "optimized_drawing_expert_review_pdf_batch_module_zip",
    )
    fixture = _build_review_metadata_fixture(tmp_path)
    metadata_json = fixture["expert_metadata_json"]
    out_dir = tmp_path / "expert_review_pdf_batch"
    out_manifest = out_dir / "optimized_drawing_expert_review.batch_manifest.json"
    out_receipt = out_dir / "optimized_drawing_expert_review.batch_receipt.txt"

    result = batch.export_expert_review_pdf_batch(
        expert_review_metadata_json=metadata_json,
        out_dir=out_dir,
        out_manifest_json=out_manifest,
        out_receipt_txt=out_receipt,
    )

    assert out_manifest.exists()
    assert out_receipt.exists()
    manifest = json.loads(out_manifest.read_text(encoding="utf-8"))
    receipt_text = out_receipt.read_text(encoding="utf-8")

    assert result["template_count"] == 3
    assert result["zip_bundle_count"] == 3
    assert manifest["template_order"] == [
        "default",
        "seoul_permit_review",
        "structural_peer_committee",
    ]
    assert manifest["zip_bundle_count"] == 3
    assert "zip_bundle_count=3" in receipt_text

    template_rows = {row["template_name"]: row for row in manifest["templates"]}
    assert set(template_rows) == {
        "default",
        "seoul_permit_review",
        "structural_peer_committee",
    }

    for template_name, row in template_rows.items():
        review_html = Path(row["output_review_html"])
        expert_html = Path(row["output_expert_html"])
        metadata_path = Path(row["output_metadata_json"])
        pdf_path = Path(row["out_pdf"])
        zip_path = Path(row["submission_zip"])
        assert review_html.exists()
        assert expert_html.exists()
        assert metadata_path.exists()
        assert pdf_path.exists()
        assert zip_path.exists()
        assert row["zip_entry_count"] == 4
        assert row["relative_submission_zip"].endswith(f"{template_name}.submission.zip")
        assert [entry["arcname"] for entry in row["zip_entries"]] == [
            "optimized_drawing_review.html",
            "optimized_drawing_expert_review.html",
            "optimized_drawing_expert_review.metadata.json",
            "optimized_drawing_expert_review.pdf",
        ]

        with zipfile.ZipFile(zip_path) as archive:
            assert archive.namelist() == [
                "optimized_drawing_review.html",
                "optimized_drawing_expert_review.html",
                "optimized_drawing_expert_review.metadata.json",
                "optimized_drawing_expert_review.pdf",
            ]
            names_to_bytes = {name: archive.read(name) for name in archive.namelist()}
        assert names_to_bytes["optimized_drawing_review.html"] == review_html.read_bytes()
        assert names_to_bytes["optimized_drawing_expert_review.html"] == expert_html.read_bytes()
        assert names_to_bytes["optimized_drawing_expert_review.metadata.json"] == metadata_path.read_bytes()
        assert names_to_bytes["optimized_drawing_expert_review.pdf"] == pdf_path.read_bytes()

    default_metadata = json.loads(Path(template_rows["default"]["output_metadata_json"]).read_text(encoding="utf-8"))
    seoul_metadata = json.loads(Path(template_rows["seoul_permit_review"]["output_metadata_json"]).read_text(encoding="utf-8"))
    peer_metadata = json.loads(Path(template_rows["structural_peer_committee"]["output_metadata_json"]).read_text(encoding="utf-8"))

    assert default_metadata["issue_fields"]["authority_name"] == "서울 구조 심의위원회"
    assert seoul_metadata["issue_fields"]["authority_name"] == "Seoul Metropolitan Permit Review Office"
    assert seoul_metadata["issue_fields"]["package_purpose_label"] == "Seoul Permit Review Package"
    assert peer_metadata["issue_fields"]["authority_name"] == "Structural Peer Committee"
    assert peer_metadata["issue_fields"]["package_purpose_label"] == "Structural Peer Committee Review Package"
    assert "zip=optimized_drawing_expert_review.seoul_permit_review.submission.zip" in receipt_text
    assert "zip=optimized_drawing_expert_review.structural_peer_committee.submission.zip" in receipt_text

    manifest_bytes_before = out_manifest.read_bytes()
    receipt_bytes_before = out_receipt.read_bytes()
    zip_bytes_before = {
        template_name: Path(row["submission_zip"]).read_bytes()
        for template_name, row in template_rows.items()
    }

    rerun = batch.export_expert_review_pdf_batch(
        expert_review_metadata_json=metadata_json,
        out_dir=out_dir,
        out_manifest_json=out_manifest,
        out_receipt_txt=out_receipt,
    )
    assert rerun["template_order"] == manifest["template_order"]
    assert out_manifest.read_bytes() == manifest_bytes_before
    assert out_receipt.read_bytes() == receipt_bytes_before
    for template_name, row in template_rows.items():
        assert Path(row["submission_zip"]).read_bytes() == zip_bytes_before[template_name]


def test_export_rendered_expert_review_pdf_batch_from_onboarding_renders_template_specific_html(tmp_path: Path) -> None:
    batch = _load_module(
        "implementation/phase1/export_optimized_drawing_expert_review_pdf_batch.py",
        "optimized_drawing_expert_review_pdf_batch_module_rendered",
    )
    fixture = _build_review_metadata_fixture(tmp_path)
    viewer_json = fixture["viewer_json"]
    onboarding_json = fixture["project_onboarding_json"]
    out_dir = tmp_path / "expert_review_rendered_batch"
    out_manifest = out_dir / "optimized_drawing_expert_review.batch_manifest.json"
    out_receipt = out_dir / "optimized_drawing_expert_review.batch_receipt.txt"

    result = batch.export_rendered_expert_review_pdf_batch(
        viewer_json_path=viewer_json,
        project_onboarding_json=onboarding_json,
        out_dir=out_dir,
        out_manifest_json=out_manifest,
        out_receipt_txt=out_receipt,
    )

    assert out_manifest.exists()
    assert out_receipt.exists()
    manifest = json.loads(out_manifest.read_text(encoding="utf-8"))
    assert result["template_count"] == 3
    assert manifest["schema_version"] == "optimized_drawing_expert_review_pdf.rendered_batch_manifest.v1"
    assert manifest["source_project_onboarding_json"] == str(onboarding_json)
    assert manifest["onboarding_selected_template"] == "seoul_permit_review"
    assert manifest["onboarding_selection_reason"] == "Seoul permit package requested by customer."

    template_rows = {row["template_name"]: row for row in manifest["templates"]}
    default_expert_html = Path(template_rows["default"]["output_expert_html"]).read_text(encoding="utf-8")
    seoul_expert_html = Path(template_rows["seoul_permit_review"]["output_expert_html"]).read_text(encoding="utf-8")
    peer_expert_html = Path(template_rows["structural_peer_committee"]["output_expert_html"]).read_text(encoding="utf-8")

    assert "Permit / committee checklist" in default_expert_html
    assert "Permit / committee sign-off block" in default_expert_html
    assert "Permit checklist" in seoul_expert_html
    assert "Peer review checklist" in peer_expert_html

    with zipfile.ZipFile(template_rows["seoul_permit_review"]["submission_zip"]) as archive:
        assert archive.namelist() == [
            "optimized_drawing_review.html",
            "optimized_drawing_expert_review.html",
            "optimized_drawing_expert_review.metadata.json",
            "optimized_drawing_expert_review.pdf",
            "project_onboarding.request.json",
            "project_onboarding.intake_receipt.json",
        ]
        seoul_zip_expert_html = archive.read("optimized_drawing_expert_review.html").decode("utf-8")
        seoul_zip_request = json.loads(archive.read("project_onboarding.request.json").decode("utf-8"))
        seoul_zip_receipt = json.loads(archive.read("project_onboarding.intake_receipt.json").decode("utf-8"))
    with zipfile.ZipFile(template_rows["structural_peer_committee"]["submission_zip"]) as archive:
        peer_zip_expert_html = archive.read("optimized_drawing_expert_review.html").decode("utf-8")

    assert "Seoul permit issue checklist" in seoul_zip_expert_html
    assert "Independent structural peer checklist" in peer_zip_expert_html
    assert seoul_zip_request["request"]["request_id"] == "REQ-24010"
    assert seoul_zip_receipt["payload_kind"] == "customer_portal_api_payload"
    assert seoul_zip_receipt["request"]["submission_channel"] == "customer_portal"
    assert seoul_zip_receipt["target_template_name"] == "seoul_permit_review"
    assert seoul_zip_receipt["validation"]["status"] == "pass"
    assert seoul_zip_receipt["validation"]["warning_count"] == 0
    assert seoul_zip_receipt["missing_required_fields"] == []
    assert "request.request_id" in seoul_zip_receipt["validation"]["checked_fields"]
    assert template_rows["seoul_permit_review"]["intake_validation_status"] == "pass"
    assert template_rows["seoul_permit_review"]["intake_warning_count"] == 0
    assert template_rows["seoul_permit_review"]["intake_missing_required_field_count"] == 0


def test_export_rendered_expert_review_pdf_batch_flags_missing_required_onboarding_fields(tmp_path: Path) -> None:
    batch = _load_module(
        "implementation/phase1/export_optimized_drawing_expert_review_pdf_batch.py",
        "optimized_drawing_expert_review_pdf_batch_module_validation",
    )
    fixture = _build_review_metadata_fixture(tmp_path)
    viewer_json = fixture["viewer_json"]
    onboarding_json = fixture["project_onboarding_json"]
    payload = json.loads(onboarding_json.read_text(encoding="utf-8"))
    payload["request"].pop("request_id", None)
    payload["review_team"].pop("reviewed_by", None)
    onboarding_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out_dir = tmp_path / "expert_review_rendered_batch_warn"
    result = batch.export_rendered_expert_review_pdf_batch(
        viewer_json_path=viewer_json,
        project_onboarding_json=onboarding_json,
        out_dir=out_dir,
        out_manifest_json=out_dir / "manifest.json",
        out_receipt_txt=out_dir / "receipt.txt",
        template_names=["seoul_permit_review"],
    )

    row = result["templates"][0]
    receipt_payload = json.loads(
        zipfile.ZipFile(row["submission_zip"]).read("project_onboarding.intake_receipt.json").decode("utf-8")
    )
    assert receipt_payload["validation"]["status"] == "warn"
    assert "request.request_id" in receipt_payload["missing_required_fields"]
    assert "review_team.reviewed_by" in receipt_payload["missing_required_fields"]
    assert row["intake_validation_status"] == "warn"
    assert row["intake_missing_required_field_count"] == 2
