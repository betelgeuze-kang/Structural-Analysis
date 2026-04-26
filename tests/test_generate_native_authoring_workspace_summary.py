from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_workspace_summary import (
    build_native_authoring_workspace_payload,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_workspace_summary.py")


def _build_frontend_draft_payload() -> dict[str, object]:
    return {
        "format": "native-authoring-workspace-draft",
        "version": 1,
        "authoring_controls": {
            "story_count": 7,
            "bay_count": 4,
            "floor_height_m": 3.4,
            "load_pattern_count": 6,
            "section_id": "steel_box_400x400x16",
        },
    }


def test_build_native_authoring_workspace_payload_surfaces_ready_summary() -> None:
    payload = build_native_authoring_workspace_payload(generated_at="2026-04-19T07:00:00+00:00")

    assert payload["contract_pass"] is True
    assert payload["generated_at"] == "2026-04-19T07:00:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "sample_tower"
    assert payload["summary"]["native_authoring_ready"] is True
    assert payload["summary"]["story_count"] == 5
    assert payload["summary"]["member_count"] > 0
    assert payload["editor_controls"]["default_section_id"] == "steel_h_600x200"
    assert payload["editor_controls"]["default_family_id"] == "sample_tower"
    assert payload["editor_controls"]["load_pattern_count"] == 4
    assert len(payload["editor_controls"]["family_palette"]) == 8
    assert "Native authoring bundle: PASS" in payload["summary_line"]


def test_build_native_authoring_workspace_payload_accepts_frontend_authoring_controls() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-19T07:10:00+00:00",
        authoring_controls={
            "storyCount": 7,
            "bayCount": 4,
            "floorHeightM": 3.4,
            "loadPatternCount": 6,
            "sectionId": "steel_box_400x400x16",
        },
    )

    assert payload["generated_at"] == "2026-04-19T07:10:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "sample_tower"
    assert payload["authoring_controls"]["story_count"] == 7
    assert payload["authoring_controls"]["bay_count"] == 4
    assert payload["authoring_controls"]["floor_height_m"] == 3.4
    assert payload["authoring_controls"]["load_pattern_count"] == 6
    assert payload["authoring_controls"]["section_id"] == "steel_box_400x400x16"
    assert payload["summary"]["model_id"] == "native-authoring-07s-04b-034h-06lp-steel-box-400x400x16"
    assert payload["summary"]["story_count"] == 7
    assert payload["summary"]["node_count"] == 40
    assert payload["summary"]["member_count"] == 63
    assert payload["summary"]["load_pattern_count"] == 6
    assert payload["summary"]["section_usage_counts"] == {
        "rc_column_700x700": 35,
        "steel_box_400x400x16": 28,
    }
    assert len(payload["model_preview"]["load_patterns"]) == 6
    assert payload["editor_controls"]["default_section_id"] == "steel_box_400x400x16"


def test_build_native_authoring_workspace_payload_uses_family_defaults_and_surfaces_catalog() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-19T07:20:00+00:00",
        authoring_controls={
            "familyId": "steel_braced_frame",
        },
    )

    assert payload["generated_at"] == "2026-04-19T07:20:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert payload["authoring_controls"]["story_count"] == 6
    assert payload["authoring_controls"]["bay_count"] == 4
    assert payload["authoring_controls"]["floor_height_m"] == 4.5
    assert payload["authoring_controls"]["load_pattern_count"] == 6
    assert payload["authoring_controls"]["section_id"] == "steel_h_600x200"
    assert payload["summary"]["model_id"] == "native-authoring-steel-braced-frame-06s-04b-045h-06lp-steel-h-600x200"
    assert payload["summary"]["node_count"] == 35
    assert payload["summary"]["member_count"] == 126
    assert payload["summary"]["section_usage_counts"] == {
        "deck_beam_500x250": 24,
        "steel_box_400x400x16": 30,
        "steel_h_600x200": 72,
    }
    assert payload["selected_family"]["family_id"] == "steel_braced_frame"
    assert payload["editor_controls"]["default_family_id"] == "steel_braced_frame"
    assert payload["editor_controls"]["bay_width_m"] == 8.5
    family_ids = [row["family_id"] for row in payload["editor_controls"]["family_palette"]]
    assert family_ids == [
        "sample_tower",
        "steel_braced_frame",
        "rc_wall_core",
        "composite_podium",
        "outrigger_transfer_tower",
        "dual_system_hospital",
        "belt_truss_mega_frame",
        "deep_transfer_basement",
    ]


def test_build_native_authoring_workspace_payload_supports_steel_braced_frame_family() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-19T07:20:00+00:00",
        authoring_controls={
            "familyId": "steel_braced_frame",
            "storyCount": 6,
            "bayCount": 4,
            "floorHeightM": 3.6,
            "loadPatternCount": 6,
            "sectionId": "steel_h_600x200",
        },
    )

    assert payload["generated_at"] == "2026-04-19T07:20:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["model_id"] == "native-authoring-steel-braced-frame-06s-04b-036h-06lp-steel-h-600x200"
    assert payload["summary"]["story_count"] == 6
    assert payload["summary"]["node_count"] == 35
    assert payload["summary"]["member_count"] == 126
    assert payload["summary"]["member_type_counts"] == {
        "beam": 24,
        "brace": 48,
        "column": 30,
        "slab": 24,
    }
    assert payload["summary"]["section_usage_counts"] == {
        "deck_beam_500x250": 24,
        "steel_box_400x400x16": 30,
        "steel_h_600x200": 72,
    }
    assert payload["editor_controls"]["default_family_id"] == "steel_braced_frame"
    assert payload["editor_controls"]["default_section_id"] == "steel_h_600x200"
    assert "family=steel_braced_frame" in payload["summary_line"]


def test_build_native_authoring_workspace_payload_uses_family_default_section_when_only_family_changes() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-19T07:25:00+00:00",
        authoring_controls={
            "familyId": "composite_podium",
            "storyCount": 4,
            "bayCount": 3,
            "loadPatternCount": 6,
        },
    )

    assert payload["authoring_controls"]["family_id"] == "composite_podium"
    assert payload["authoring_controls"]["section_id"] == "deck_beam_500x250"
    assert payload["summary"]["model_id"] == "native-authoring-composite-podium-04s-03b-042h-06lp-deck-beam-500x250"
    assert payload["summary"]["member_count"] == 40
    assert payload["summary"]["member_type_counts"] == {
        "beam": 12,
        "column": 16,
        "slab": 12,
    }
    assert payload["editor_controls"]["default_section_id"] == "deck_beam_500x250"
    assert payload["selected_family"]["family_id"] == "composite_podium"


def test_build_native_authoring_workspace_payload_supports_outrigger_transfer_tower_family() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-20T07:25:00+00:00",
        authoring_controls={
            "familyId": "outrigger_transfer_tower",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "outrigger_transfer_tower"
    assert payload["authoring_controls"]["section_id"] == "steel_h_600x200"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["model_id"] == "native-authoring-outrigger-transfer-tower-10s-05b-041h-06lp-steel-h-600x200"
    assert payload["summary"]["member_count"] == 170
    assert payload["summary"]["member_type_counts"] == {
        "beam": 50,
        "brace": 10,
        "column": 60,
        "slab": 50,
    }
    assert payload["summary"]["section_usage_counts"] == {
        "cft_box_700x700": 60,
        "deck_beam_500x250": 50,
        "steel_box_400x400x16": 20,
        "steel_h_600x200": 40,
    }


def test_build_native_authoring_workspace_payload_supports_dual_system_hospital_family() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-20T07:26:00+00:00",
        authoring_controls={
            "familyId": "dual_system_hospital",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "dual_system_hospital"
    assert payload["authoring_controls"]["section_id"] == "steel_h_600x200"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022"
    assert payload["summary"]["model_id"] == "native-authoring-dual-system-hospital-08s-05b-040h-06lp-steel-h-600x200"
    assert payload["summary"]["member_count"] == 144
    assert payload["summary"]["member_type_counts"] == {
        "beam": 40,
        "column": 48,
        "slab": 40,
        "wall": 16,
    }
    assert payload["summary"]["section_usage_counts"] == {
        "cft_box_700x700": 16,
        "deck_beam_500x250": 40,
        "rc_column_700x700": 32,
        "rc_wall_300x3000": 16,
        "steel_h_600x200": 40,
    }


def test_build_native_authoring_workspace_payload_supports_belt_truss_mega_frame_family() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-20T07:27:00+00:00",
        authoring_controls={
            "familyId": "belt_truss_mega_frame",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "belt_truss_mega_frame"
    assert payload["authoring_controls"]["section_id"] == "steel_h_600x200"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["model_id"] == "native-authoring-belt-truss-mega-frame-12s-06b-042h-06lp-steel-h-600x200"
    assert payload["summary"]["node_count"] == 91
    assert payload["summary"]["member_count"] == 270
    assert payload["summary"]["member_type_counts"] == {
        "beam": 72,
        "brace": 18,
        "column": 84,
        "slab": 72,
        "wall": 24,
    }
    assert payload["summary"]["section_usage_counts"] == {
        "cft_box_700x700": 24,
        "deck_beam_500x250": 72,
        "rc_column_700x700": 60,
        "rc_wall_300x3000": 24,
        "steel_box_400x400x16": 18,
        "steel_h_600x200": 72,
    }
    assert "family=belt_truss_mega_frame" in payload["summary_line"]


def test_build_native_authoring_workspace_payload_supports_deep_transfer_basement_family() -> None:
    payload = build_native_authoring_workspace_payload(
        generated_at="2026-04-20T07:28:00+00:00",
        authoring_controls={
            "familyId": "deep_transfer_basement",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "deep_transfer_basement"
    assert payload["authoring_controls"]["section_id"] == "steel_h_600x200"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022"
    assert payload["summary"]["model_id"] == "native-authoring-deep-transfer-basement-06s-04b-044h-06lp-steel-h-600x200"
    assert payload["summary"]["node_count"] == 35
    assert payload["summary"]["member_count"] == 94
    assert payload["summary"]["member_type_counts"] == {
        "beam": 24,
        "column": 30,
        "foundation": 4,
        "slab": 24,
        "wall": 12,
    }
    assert payload["summary"]["section_usage_counts"] == {
        "cft_box_700x700": 12,
        "deck_beam_500x250": 24,
        "rc_column_700x700": 18,
        "rc_wall_300x3000": 16,
        "steel_box_400x400x16": 8,
        "steel_h_600x200": 16,
    }
    assert "family=deep_transfer_basement" in payload["summary_line"]


def test_generate_native_authoring_workspace_summary_cli(tmp_path: Path) -> None:
    out = tmp_path / "native_authoring_workspace_summary.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-19T07:30:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-04-19T07:30:00+00:00"
    assert payload["summary"]["native_authoring_ready"] is True
    assert payload["summary"]["load_pattern_count"] == 4


def test_generate_native_authoring_workspace_summary_cli_accepts_frontend_draft_json(tmp_path: Path) -> None:
    draft_json = tmp_path / "native_authoring_workspace_draft.json"
    out = tmp_path / "native_authoring_workspace_summary.json"
    draft_json.write_text(json.dumps(_build_frontend_draft_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--draft-json",
            str(draft_json),
            "--generated-at",
            "2026-04-19T07:45:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-04-19T07:45:00+00:00"
    assert payload["authoring_controls"]["story_count"] == 7
    assert payload["summary"]["story_count"] == 7
    assert payload["summary"]["load_pattern_count"] == 6
    assert payload["editor_controls"]["default_section_id"] == "steel_box_400x400x16"


def test_generate_native_authoring_workspace_summary_cli_accepts_family_id_override(tmp_path: Path) -> None:
    out = tmp_path / "native_authoring_workspace_summary.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--family-id",
            "rc_wall_core",
            "--story-count",
            "6",
            "--bay-count",
            "4",
            "--load-pattern-count",
            "6",
            "--generated-at",
            "2026-04-19T07:50:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-04-19T07:50:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "rc_wall_core"
    assert payload["authoring_controls"]["section_id"] == "rc_column_700x700"
    assert payload["summary"]["member_type_counts"] == {
        "beam": 24,
        "column": 18,
        "slab": 24,
        "wall": 12,
    }
