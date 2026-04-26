from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_load_combination_editor_commercialization_report import (
    build_load_combination_editor_commercialization_report,
)
from implementation.phase1.generate_native_authoring_solver_session import (
    build_native_authoring_solver_session_payload,
)


SCRIPT = Path("implementation/phase1/generate_load_combination_editor_commercialization_report.py")


def _build_full_rc_solver_payload() -> dict[str, object]:
    return build_native_authoring_solver_session_payload(
        generated_at="2026-04-21T00:00:00+00:00",
        authoring_controls={
            "storyCount": 7,
            "bayCount": 4,
            "floorHeightM": 3.4,
            "loadPatternCount": 6,
            "sectionId": "steel_box_400x400x16",
        },
        editor_contract_profile="commercialization_target",
    )


def test_build_load_combination_editor_commercialization_report_is_deterministic_for_locked_timestamp() -> None:
    solver_payload = _build_full_rc_solver_payload()

    report_a = build_load_combination_editor_commercialization_report(
        solver_payload,
        generated_at="2026-04-21T09:30:00+00:00",
    )
    report_b = build_load_combination_editor_commercialization_report(
        solver_payload,
        generated_at="2026-04-21T09:30:00+00:00",
    )

    assert report_a == report_b
    assert report_a["generated_at"] == "2026-04-21T09:30:00+00:00"
    assert report_a["summary"]["required_target_count"] == 8
    assert report_a["summary"]["required_target_ready_count"] == 8
    assert report_a["summary"]["required_target_match_label"] == "8/8"
    assert report_a["required_target_match"]["rc_target_match_label"] == "8/8"
    assert report_a["solver_load_card_coverage"]["ready"] is True
    assert set(report_a["solver_load_card_coverage"]["covered_card_types"]) >= {
        "selfweight",
        "nodal",
        "surface",
        "pressure",
    }
    assert report_a["summary"]["code_check_assembly_ready"] is True
    assert report_a["code_check_assembly"]["ready"] is True
    assert report_a["contract_pass"] is True
    assert report_a["summary"]["nested_combo_count"] == 3
    assert report_a["summary"]["max_nested_depth"] == 3
    assert report_a["summary"]["load_diff_difference_count"] == 0
    assert report_a["summary"]["family_template_diff_difference_count"] > 0
    assert report_a["control_locked_baseline_diff"]["ready"] is True
    assert report_a["control_locked_baseline_diff"]["baseline_kind"] == "authoring_controls_locked_baseline"
    assert report_a["family_baseline_diff"]["baseline_kind"] == "family_template"
    assert report_a["determinism"]["generated_at_locked"] is True
    assert report_a["determinism"]["payload_sha256"] == report_b["determinism"]["payload_sha256"]
    assert "kds_match=8/8" in report_a["summary_line"]
    assert "nested=3 depth=3" in report_a["summary_line"]
    assert "diff=0" in report_a["summary_line"]


def test_build_load_combination_editor_commercialization_report_tracks_nested_combo_depth() -> None:
    solver_payload = build_native_authoring_solver_session_payload(
        generated_at="2026-04-21T00:00:00+00:00",
        authoring_controls={
            "storyCount": 7,
            "bayCount": 4,
            "floorHeightM": 3.4,
            "loadPatternCount": 6,
            "sectionId": "steel_box_400x400x16",
        },
    )
    solver_payload = json.loads(json.dumps(solver_payload))
    editor_seed = solver_payload["load_combination_session"]["editor_seed"]
    combination_nodes = editor_seed["combination_nodes"]
    combination_nodes.append(
        {
            "id": "COMBO:ENV_ULS",
            "name": "ENV_ULS",
            "kind": "combo",
            "editor_stage": 2,
            "limit_state": "ULS",
            "combination_type": "GEN",
            "expression": "1(KDS_ULS_2) + 1(KDS_ULS_3_WX+)",
            "entry_count": 2,
            "expansion_mode": "nested_envelope",
            "expansion_depth": 2,
            "referenced_combinations": ["KDS_ULS_2", "KDS_ULS_3_WX+"],
            "referenced_leaf_cases": ["D", "L", "Wx"],
            "factor_map": {},
            "expanded_factor_map": {"D": 2.4, "L": 2.1, "Wx": 1.0},
            "entry_rows": [
                {"reference_kind": "CB", "reference_name": "KDS_ULS_2", "factor": 1.0},
                {"reference_kind": "CB", "reference_name": "KDS_ULS_3_WX+", "factor": 1.0},
            ],
            "node_role": "user_combo",
        }
    )
    combination_nodes.append(
        {
            "id": "COMBO:DEEP_ENV",
            "name": "DEEP_ENV",
            "kind": "combo",
            "editor_stage": 3,
            "limit_state": "ULS",
            "combination_type": "GEN",
            "expression": "1(ENV_ULS) + 1(KDS_ULS_5_EX+)",
            "entry_count": 2,
            "expansion_mode": "nested_envelope",
            "expansion_depth": 3,
            "referenced_combinations": ["ENV_ULS", "KDS_ULS_5_EX+"],
            "referenced_leaf_cases": ["D", "L", "Wx", "Ex"],
            "factor_map": {},
            "expanded_factor_map": {"D": 3.6, "L": 2.6, "Wx": 1.0, "Ex": 1.0},
            "entry_rows": [
                {"reference_kind": "CB", "reference_name": "ENV_ULS", "factor": 1.0},
                {"reference_kind": "CB", "reference_name": "KDS_ULS_5_EX+", "factor": 1.0},
            ],
            "node_role": "user_combo",
        }
    )

    report = build_load_combination_editor_commercialization_report(
        solver_payload,
        generated_at="2026-04-21T10:00:00+00:00",
    )

    assert report["checks"]["nested_envelope_native_expansion_pass"] is True
    assert report["nested_expansion"]["ready"] is True
    assert report["summary"]["nested_combo_count"] == 5
    assert report["summary"]["max_nested_depth"] == 3
    assert report["nested_expansion"]["unresolved_reference_count"] == 0
    assert any(
        row["name"] == "DEEP_ENV" and row["nested_depth"] == 3
        for row in report["nested_expansion"]["combo_depth_rows"]
    )
    assert report["summary"]["code_check_assembly_ready"] is True
    assert "nested=5 depth=3" in report["summary_line"]


def test_generate_load_combination_editor_commercialization_report_cli_materializes_local_report(
    tmp_path: Path,
) -> None:
    solver_session = tmp_path / "native_authoring_solver_session.json"
    out = tmp_path / "load_combination_editor_commercialization_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--solver-session",
            str(solver_session),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-21T11:00:00+00:00",
            "--story-count",
            "7",
            "--bay-count",
            "4",
            "--floor-height-m",
            "3.4",
            "--load-pattern-count",
            "6",
            "--section-id",
            "steel_box_400x400x16",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert "kds_match=8/8" in completed.stdout
    assert payload["generated_at"] == "2026-04-21T11:00:00+00:00"
    assert payload["artifacts"]["solver_session_json"] == str(solver_session)
    assert payload["artifacts"]["solver_session_source"] == "local_builder"
    assert payload["artifacts"]["load_combination_editor_commercialization_report_json"] == str(out)
    assert payload["contract_pass"] is True
    assert payload["summary"]["required_target_match_label"] == "8/8"
    assert payload["summary"]["load_diff_difference_count"] == 0
    assert payload["summary"]["code_check_assembly_ready"] is True
    assert payload["nested_expansion"]["ready"] is True
    assert payload["summary"]["max_nested_depth"] == 3
    assert payload["solver_load_card_coverage"]["ready"] is True
    assert payload["determinism"]["generated_at_locked"] is True
