from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_solver_session import (
    DEFAULT_LOADCOMB_OUT,
    DEFAULT_OUT,
    build_native_authoring_solver_session_payload,
    materialize_native_authoring_solver_session,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_solver_session.py")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def test_build_native_authoring_solver_session_payload_is_deterministic() -> None:
    payload_a = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:00:00+00:00",
    )
    payload_b = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:00:00+00:00",
    )

    assert payload_a == payload_b
    assert payload_a["generated_at"] == "2026-04-19T08:00:00+00:00"
    assert payload_a["contract_pass"] is True
    assert payload_a["authoring_controls"]["family_id"] == "sample_tower"
    assert payload_a["authoring_summary"]["native_authoring_ready"] is True
    assert payload_a["summary"]["mesh_request_count"] == 2
    assert payload_a["summary"]["combo_count"] == 16
    assert payload_a["summary"]["editor_contract_profile"] == "commercialization_target"
    assert payload_a["mesh_session"]["request_count"] == 2
    assert payload_a["mesh_session"]["total_estimated_cells"] > 0
    assert payload_a["load_pattern_summary"]["case_counts"] == {"D": 1, "Ex": 1, "L": 2, "Wx": 1}
    assert payload_a["load_combination_session"]["family"] == "KDS-2022"
    assert payload_a["load_combination_session"]["runtime_summary"]["combo_count"] == 16
    assert payload_a["load_combination_session"]["runtime_summary"]["authoring_ready"] is True
    assert payload_a["load_combination_session"]["runtime_summary"]["nested_combo_count"] == 3
    assert payload_a["load_combination_session"]["runtime_summary"]["max_nested_depth"] == 3
    assert payload_a["load_combination_session"]["runtime_summary"]["runtime_case_names"] == ["D", "Ex", "L", "Wx"]
    assert payload_a["load_combination_session"]["loadcomb_preview_line_count"] > 1
    assert payload_a["load_combination_session"]["selected_combination_names"][0] == "KDS_ULS_1"
    assert payload_a["load_combination_session"]["selected_combination_names"][-1] == "KDS_ENV_ULS_CRITICAL"
    assert payload_a["load_combination_session"]["omitted_library_combinations"][0]["name"] == "KDS_ULS_4_WY+"
    assert payload_a["source_provenance"]["helper_contracts"]["authoring_model_builder"].endswith(
        "build_sample_authoring_model"
    )
    assert payload_a["source_provenance"]["load_combination_library_sources"] == [
        "implementation.phase1.load_combination_engine.generate_kds_strength_combinations",
        "implementation.phase1.load_combination_engine.generate_kds_service_combinations",
    ]
    assert payload_a["determinism"]["signature_mode"] == "sha256_stable_json_v1"
    assert payload_a["determinism"]["generated_at_locked"] is True
    assert payload_a["determinism"]["payload_sha256"] == payload_b["determinism"]["payload_sha256"]
    assert payload_a["artifacts"]["session_summary_json"] == str(DEFAULT_OUT)
    assert payload_a["artifacts"]["loadcomb_preview_mgt"] == str(DEFAULT_LOADCOMB_OUT)
    assert "Native authoring solver session: PASS" in payload_a["summary_line"]


def test_materialize_native_authoring_solver_session_writes_deterministic_json_and_loadcomb_preview(
    tmp_path: Path,
) -> None:
    out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"

    payload_a = materialize_native_authoring_solver_session(
        out_path=out,
        loadcomb_out_path=loadcomb_out,
        generated_at="2026-04-19T08:15:00+00:00",
    )
    payload_text_a = out.read_text(encoding="utf-8")
    loadcomb_text_a = loadcomb_out.read_text(encoding="utf-8")

    payload_b = materialize_native_authoring_solver_session(
        out_path=out,
        loadcomb_out_path=loadcomb_out,
        generated_at="2026-04-19T08:15:00+00:00",
    )
    payload_text_b = out.read_text(encoding="utf-8")
    loadcomb_text_b = loadcomb_out.read_text(encoding="utf-8")
    written_payload = json.loads(payload_text_b)

    assert payload_a == payload_b
    assert payload_text_a == payload_text_b
    assert loadcomb_text_a == loadcomb_text_b
    assert payload_a["generated_at"] == "2026-04-19T08:15:00+00:00"
    assert written_payload["generated_at"] == "2026-04-19T08:15:00+00:00"
    assert written_payload["contract_pass"] is True
    assert written_payload["artifacts"]["session_summary_json"] == str(out)
    assert written_payload["artifacts"]["loadcomb_preview_mgt"] == str(loadcomb_out)
    assert written_payload["determinism"]["payload_sha256"] == payload_b["determinism"]["payload_sha256"]
    assert written_payload["determinism"]["loadcomb_preview_sha256"] == _sha256_text(loadcomb_text_b)
    assert loadcomb_text_b.startswith("*LOADCOMB\n")
    assert "NAME=KDS_ULS_1, GEN, ULS, 0, 0, 1.4(DEAD), 0, 0, 0" in loadcomb_text_b
    assert "ST, DEAD, 1.4" in loadcomb_text_b
    assert "NAME=KDS_SLS_4_EX-, GEN, SLS, 0, 0, 1(DEAD) + 0.5(LIVE) - 0.7(EX), 0, 0, 0" in loadcomb_text_b


def test_build_native_authoring_solver_session_payload_accepts_frontend_authoring_controls() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:20:00+00:00",
        authoring_controls={
            "storyCount": 7,
            "bayCount": 4,
            "floorHeightM": 3.4,
            "loadPatternCount": 6,
            "sectionId": "steel_box_400x400x16",
        },
    )

    assert payload["generated_at"] == "2026-04-19T08:20:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "sample_tower"
    assert payload["authoring_controls"]["story_count"] == 7
    assert payload["authoring_summary"]["model_id"] == "native-authoring-07s-04b-034h-06lp-steel-box-400x400x16"
    assert payload["summary"]["story_count"] == 7
    assert payload["summary"]["member_count"] == 63
    assert payload["summary"]["load_pattern_count"] == 6
    assert payload["summary"]["mesh_request_count"] == 2
    assert payload["summary"]["combo_count"] == 26
    assert payload["summary"]["editor_contract_profile"] == "commercialization_target"
    assert payload["load_pattern_summary"]["case_counts"] == {
        "D": 1,
        "Ex": 1,
        "Ey": 1,
        "L": 2,
        "Wx": 1,
        "Wy": 1,
    }
    assert payload["load_combination_session"]["runtime_summary"]["combo_count"] == 26
    assert payload["load_combination_session"]["runtime_summary"]["nested_combo_count"] == 3
    assert payload["load_combination_session"]["runtime_summary"]["max_nested_depth"] == 3
    assert payload["load_combination_session"]["runtime_summary"]["runtime_case_names"] == [
        "D",
        "Ex",
        "Ey",
        "L",
        "Wx",
        "Wy",
    ]
    assert payload["load_combination_session"]["omitted_library_combinations"] == []


def test_build_native_authoring_solver_session_payload_supports_commercialization_target_profile() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-21T08:20:00+00:00",
        authoring_controls={
            "storyCount": 7,
            "bayCount": 4,
            "floorHeightM": 3.4,
            "loadPatternCount": 6,
            "sectionId": "steel_box_400x400x16",
        },
        editor_contract_profile="commercialization_target",
    )

    assert payload["summary"]["editor_contract_profile"] == "commercialization_target"
    assert payload["load_combination_session"]["editor_contract_profile"] == "commercialization_target"
    assert payload["source_provenance"]["editor_contract_profile"] == "commercialization_target"
    assert payload["load_combination_session"]["runtime_summary"]["combo_count"] == 26
    assert payload["load_combination_session"]["runtime_summary"]["nested_combo_count"] == 3
    assert payload["load_combination_session"]["runtime_summary"]["max_nested_depth"] == 3
    assert "KDS_ENV_ULS_LATERAL" in payload["load_combination_session"]["selected_combination_names"]
    assert "KDS_ENV_ULS_CRITICAL" in payload["load_combination_session"]["selected_combination_names"]


def test_build_native_authoring_solver_session_payload_uses_family_defaults() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:25:00+00:00",
        authoring_controls={
            "familyId": "composite_podium",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "composite_podium"
    assert payload["authoring_controls"]["story_count"] == 7
    assert payload["authoring_controls"]["bay_count"] == 4
    assert payload["authoring_controls"]["section_id"] == "deck_beam_500x250"
    assert payload["selected_family"]["family_id"] == "composite_podium"
    assert payload["authoring_summary"]["model_id"] == "native-authoring-composite-podium-07s-04b-042h-06lp-deck-beam-500x250"
    assert payload["summary"]["member_count"] == 91
    assert payload["summary"]["combo_count"] == 26
    assert payload["summary"]["mesh_request_count"] == 3
    assert payload["source_provenance"]["model_id"] == "native-authoring-composite-podium-07s-04b-042h-06lp-deck-beam-500x250"
    assert payload["summary_line"].endswith("| authoring_family=composite_podium")


def test_build_native_authoring_solver_session_payload_supports_steel_braced_frame_family() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:25:00+00:00",
        authoring_controls={
            "familyId": "steel_braced_frame",
            "storyCount": 6,
            "bayCount": 4,
            "floorHeightM": 3.6,
            "loadPatternCount": 6,
            "sectionId": "steel_h_600x200",
        },
    )

    assert payload["generated_at"] == "2026-04-19T08:25:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["authoring_family_id"] == "steel_braced_frame"
    assert payload["summary"]["member_count"] == 126
    assert payload["summary"]["mesh_request_count"] == 3
    assert payload["summary"]["combo_count"] == 26
    assert payload["mesh_session"]["request_count"] == 3
    assert payload["load_pattern_summary"]["case_counts"] == {
        "D": 1,
        "Ex": 1,
        "Ey": 1,
        "L": 2,
        "Wx": 1,
        "Wy": 1,
    }
    assert payload["load_combination_session"]["runtime_summary"]["combo_count"] == 26
    assert payload["load_combination_session"]["omitted_library_combinations"] == []
    assert "authoring_family=steel_braced_frame" in payload["summary_line"]


def test_build_native_authoring_solver_session_payload_supports_composite_podium_shell_lane() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-19T08:27:00+00:00",
        authoring_controls={
            "familyId": "composite_podium",
            "storyCount": 4,
            "bayCount": 3,
            "loadPatternCount": 6,
        },
    )

    assert payload["authoring_controls"]["family_id"] == "composite_podium"
    assert payload["authoring_controls"]["section_id"] == "deck_beam_500x250"
    assert payload["summary"]["member_count"] == 40
    assert payload["summary"]["mesh_request_count"] == 3
    assert payload["mesh_session"]["request_count"] == 3
    assert sorted({row["element_kind"] for row in payload["mesh_session"]["mesh_plan_summaries"]}) == [
        "fiber_section",
        "frame",
        "shell",
    ]
    assert payload["selected_family"]["family_id"] == "composite_podium"


def test_build_native_authoring_solver_session_payload_supports_outrigger_transfer_tower_family() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-20T08:28:00+00:00",
        authoring_controls={
            "familyId": "outrigger_transfer_tower",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "outrigger_transfer_tower"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["member_count"] == 170
    assert payload["summary"]["mesh_request_count"] == 4
    assert payload["summary"]["combo_count"] == 26
    assert payload["mesh_session"]["request_count"] == 4
    assert sorted({row["element_kind"] for row in payload["mesh_session"]["mesh_plan_summaries"]}) == [
        "fiber_section",
        "frame",
        "shell",
    ]
    assert "authoring_family=outrigger_transfer_tower" in payload["summary_line"]


def test_build_native_authoring_solver_session_payload_supports_dual_system_hospital_family() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-20T08:29:00+00:00",
        authoring_controls={
            "familyId": "dual_system_hospital",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "dual_system_hospital"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022"
    assert payload["summary"]["member_count"] == 144
    assert payload["summary"]["mesh_request_count"] == 5
    assert payload["summary"]["combo_count"] == 20
    assert payload["mesh_session"]["request_count"] == 5
    assert payload["load_pattern_summary"]["case_counts"] == {
        "D": 2,
        "Ex": 1,
        "L": 2,
        "Wx": 1,
        "Wy": 1,
    }
    assert "authoring_family=dual_system_hospital" in payload["summary_line"]


def test_build_native_authoring_solver_session_payload_supports_belt_truss_mega_frame_family() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-20T08:30:00+00:00",
        authoring_controls={
            "familyId": "belt_truss_mega_frame",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "belt_truss_mega_frame"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022-STEEL-BASIC"
    assert payload["summary"]["member_count"] == 270
    assert payload["summary"]["mesh_request_count"] == 6
    assert payload["summary"]["combo_count"] == 26
    assert payload["mesh_session"]["request_count"] == 6
    assert sorted({row["element_kind"] for row in payload["mesh_session"]["mesh_plan_summaries"]}) == [
        "fiber_section",
        "frame",
        "shell",
    ]
    assert payload["load_pattern_summary"]["case_counts"] == {
        "D": 1,
        "Ex": 1,
        "Ey": 1,
        "L": 2,
        "Wx": 1,
        "Wy": 1,
    }
    assert "authoring_family=belt_truss_mega_frame" in payload["summary_line"]


def test_build_native_authoring_solver_session_payload_supports_deep_transfer_basement_family() -> None:
    payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-20T08:31:00+00:00",
        authoring_controls={
            "familyId": "deep_transfer_basement",
        },
    )

    assert payload["authoring_controls"]["family_id"] == "deep_transfer_basement"
    assert payload["selected_family"]["preferred_design_family"] == "KDS-2022"
    assert payload["summary"]["member_count"] == 94
    assert payload["summary"]["mesh_request_count"] == 7
    assert payload["summary"]["combo_count"] == 26
    assert payload["mesh_session"]["request_count"] == 7
    assert sorted({row["element_kind"] for row in payload["mesh_session"]["mesh_plan_summaries"]}) == [
        "fiber_section",
        "frame",
        "shell",
        "solid",
    ]
    assert payload["load_pattern_summary"]["case_counts"] == {
        "D": 1,
        "Ex": 1,
        "Ey": 1,
        "L": 2,
        "Wx": 1,
        "Wy": 1,
    }
    assert "authoring_family=deep_transfer_basement" in payload["summary_line"]


def test_generate_native_authoring_solver_session_cli_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"
    proc_a = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--generated-at",
            "2026-04-19T08:30:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload_text_a = out.read_text(encoding="utf-8")
    loadcomb_text_a = loadcomb_out.read_text(encoding="utf-8")

    proc_b = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--generated-at",
            "2026-04-19T08:30:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload_text_b = out.read_text(encoding="utf-8")
    loadcomb_text_b = loadcomb_out.read_text(encoding="utf-8")

    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert payload_text_a == payload_text_b
    assert loadcomb_text_a == loadcomb_text_b
    assert proc_a.stdout == proc_b.stdout

    payload = json.loads(payload_text_b)

    assert payload["generated_at"] == "2026-04-19T08:30:00+00:00"
    assert payload["contract_pass"] is True
    assert payload["mesh_session"]["request_count"] == 2
    assert payload["load_combination_session"]["runtime_summary"]["combo_count"] == 13
    assert payload["determinism"]["loadcomb_preview_sha256"] == _sha256_text(loadcomb_text_b)
    assert loadcomb_text_b.startswith("*LOADCOMB\n")
    assert "Native authoring solver session: PASS" in proc_b.stdout


def test_generate_native_authoring_solver_session_cli_accepts_frontend_draft_json(tmp_path: Path) -> None:
    draft_json = tmp_path / "native_authoring_workspace_draft.json"
    out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"
    draft_json.write_text(json.dumps(_build_frontend_draft_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--draft-json",
            str(draft_json),
            "--generated-at",
            "2026-04-19T08:45:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    loadcomb_text = loadcomb_out.read_text(encoding="utf-8")

    assert payload["generated_at"] == "2026-04-19T08:45:00+00:00"
    assert payload["authoring_controls"]["story_count"] == 7
    assert payload["summary"]["story_count"] == 7
    assert payload["summary"]["combo_count"] == 23
    assert payload["load_combination_session"]["runtime_summary"]["runtime_case_names"] == [
        "D",
        "Ex",
        "Ey",
        "L",
        "Wx",
        "Wy",
    ]
    assert "NAME=KDS_ULS_8_RSY+, GEN, ULS" in loadcomb_text


def test_generate_native_authoring_solver_session_cli_accepts_family_id_override(tmp_path: Path) -> None:
    out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--family-id",
            "rc_wall_core",
            "--story-count",
            "6",
            "--bay-count",
            "4",
            "--load-pattern-count",
            "6",
            "--generated-at",
            "2026-04-19T08:50:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-04-19T08:50:00+00:00"
    assert payload["authoring_controls"]["family_id"] == "rc_wall_core"
    assert payload["summary"]["mesh_request_count"] == 3
    assert payload["mesh_session"]["request_count"] == 3
    assert sorted({row["element_kind"] for row in payload["mesh_session"]["mesh_plan_summaries"]}) == [
        "fiber_section",
        "shell",
    ]
