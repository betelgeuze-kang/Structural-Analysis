from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/apply_working_section_override_patch.py"
    )
    spec = importlib.util.spec_from_file_location(
        "apply_working_section_override_patch_module", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_main_updates_existing_after_segments_in_viewer_artifact(tmp_path: Path) -> None:
    module = _load_module()
    source_artifact = tmp_path / "structural_optimization_viewer.json"
    patch_json = tmp_path / "section_override_patch.json"
    out_path = tmp_path / "structural_optimization_viewer.patched.json"

    _write_json(
        source_artifact,
        {
            "interactive_3d": {
                "comparison_availability": "baseline_vs_changed",
                "after_segment_count": 1,
                "after_family_options": [{"label": "beam_section", "count": 1}],
                "after_family_label": "beam_section=1",
                "baseline_segments": [
                    {
                        "member_id": "B-101",
                        "category": "beam",
                        "story_band_label": "S05",
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
                        "action_family": "beam_section",
                        "action_name": "beam_section_down",
                        "story_band_label": "S05",
                        "zone_label": "perimeter",
                        "member_type": "beam",
                        "before_section": "H-400x200",
                        "after_section": "H-350x175",
                        "impact_snapshot_label": "dcr 0.910 -> 0.780",
                        "before_after_snapshot_note": "section H-400x200 -> H-350x175 | dcr 0.910 -> 0.780",
                        "color": "#2463eb",
                        "p0": [0.0, 0.0, 0.0],
                        "p1": [8.0, 0.0, 0.0],
                    }
                ],
            }
        },
    )
    _write_json(
        patch_json,
        {
            "contract_version": 1,
            "patch_mode": "working_section_override_patch",
            "patch_scope": "member_section_override",
            "selection_source": "shared member_set",
            "viewer_url": "http://example.invalid/viewer?member_set=B-101",
            "patch_entries": [
                {
                    "member_id": "B-101",
                    "target_section": "H-325x150",
                    "current_section_summary": "H-350x175",
                    "source_section_summary": "H-400x200",
                    "selection_source": "shared member_set",
                }
            ],
        },
    )

    assert module.main(
        [
            "--source-artifact",
            str(source_artifact),
            "--patch-json",
            str(patch_json),
            "--out",
            str(out_path),
        ]
    ) == 0

    source_payload = json.loads(source_artifact.read_text(encoding="utf-8"))
    assert source_payload["interactive_3d"]["after_segments"][0]["after_section"] == "H-350x175"

    patched_payload = json.loads(out_path.read_text(encoding="utf-8"))
    after_row = patched_payload["interactive_3d"]["after_segments"][0]
    receipt = patched_payload["working_section_override_patch_apply_receipt"]

    assert after_row["after_section"] == "H-325x150"
    assert after_row["before_section"] == "H-400x200"
    assert "H-325x150" in after_row["before_after_snapshot_note"]
    assert patched_payload["interactive_3d"]["after_segment_count"] == 1
    assert patched_payload["interactive_3d"]["after_family_label"] == "beam_section=1"
    assert receipt["updated_existing_after_member_ids"] == ["B-101"]
    assert receipt["cloned_from_baseline_member_ids"] == []
    assert receipt["unmatched_member_ids"] == []


def test_main_clones_baseline_members_into_summary_interactive_payload(tmp_path: Path) -> None:
    module = _load_module()
    source_artifact = tmp_path / "optimized_drawing_review_summary.json"
    patch_json = tmp_path / "section_override_patch.json"
    out_path = tmp_path / "optimized_drawing_review_summary.patched.json"

    _write_json(
        source_artifact,
        {
            "schema_version": "optimized_drawing_review.v1",
            "interactive_3d_payload": {
                "comparison_availability": "baseline_only",
                "baseline_segment_count": 1,
                "after_segment_count": 0,
                "baseline_segments": [
                    {
                        "member_id": "C-201",
                        "member_type": "column",
                        "story_band_label": "S02",
                        "section_name": "C-600x600",
                        "color": "#5d8c72",
                        "p0": [4.0, 2.0, 0.0],
                        "p1": [4.0, 2.0, 6.0],
                    }
                ],
                "after_segments": [],
            },
        },
    )
    _write_json(
        patch_json,
        {
            "contract_version": 1,
            "patch_mode": "working_section_override_patch",
            "patch_scope": "member_section_override",
            "patch_entries": [
                {
                    "member_id": "C-201",
                    "target_section": "C-650x650",
                    "source_section_summary": "C-600x600",
                    "story_band_label": "S02",
                    "zone_label": "core",
                }
            ],
        },
    )

    assert module.main(
        [
            "--source-artifact",
            str(source_artifact),
            "--patch-json",
            str(patch_json),
            "--out",
            str(out_path),
        ]
    ) == 0

    patched_payload = json.loads(out_path.read_text(encoding="utf-8"))
    after_rows = patched_payload["interactive_3d_payload"]["after_segments"]
    receipt = patched_payload["working_section_override_patch_apply_receipt"]

    assert patched_payload["interactive_3d_payload"]["comparison_availability"] == "baseline_vs_changed"
    assert patched_payload["interactive_3d_payload"]["after_segment_count"] == 1
    assert after_rows[0]["member_id"] == "C-201"
    assert after_rows[0]["before_section"] == "C-600x600"
    assert after_rows[0]["after_section"] == "C-650x650"
    assert after_rows[0]["action_name"] == "viewer_section_override"
    assert after_rows[0]["zone_label"] == "core"
    assert "C-650x650" in after_rows[0]["before_after_snapshot_note"]
    assert receipt["updated_existing_after_member_ids"] == []
    assert receipt["cloned_from_baseline_member_ids"] == ["C-201"]
    assert receipt["interactive_payload_targets"] == ["interactive_3d_payload"]
