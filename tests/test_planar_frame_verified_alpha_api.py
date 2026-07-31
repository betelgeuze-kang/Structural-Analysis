from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.planar_frame import (
    PLANAR_FRAME_UNSUPPORTED_REASON_CODES,
    PlanarFrameConfig,
    analyze_planar_frame,
    validate_planar_frame_result,
)
from structural_analysis.api.planar_frame_cli import main as planar_frame_cli_main
from structural_analysis.model_ir import parse_model_ir_v2, validate_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
LEGACY_FIXTURE = ROOT / "examples" / "bounded_planar_frame_alpha.model-ir.v2.json"


def _verified_payload() -> dict:
    payload = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    payload["capability_profile"] = "planar_frame_verified_alpha.v1"
    return payload


def test_verified_profile_reuses_bounded_model_ir_contract() -> None:
    payload = _verified_payload()
    report = validate_model_ir_v2(payload)
    assert report.schema_valid is True
    assert report.semantics_valid is True
    document = parse_model_ir_v2(payload, require_analysis_ready=True)

    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(
            load_steps=2,
            maximum_iterations=60,
            residual_tolerance=1.0e-9,
        ),
    )
    validated = validate_planar_frame_result(result)

    assert result.status == "converged"
    assert result.converged is True
    assert validated.contract_pass is True
    assert result.public is True
    assert result.release_eligible is False
    assert result.authority["profile"] == "public_developer_preview"
    assert result.authority["release_readiness"] == "not_authoritative"
    assert result.result_ir["profile"] == "corotational_connected_frame2d.v1"
    assert result.result_ir["engineering_result_ir"] is not None
    assert result.result_ir["contract_bindings"]["bounded_planar_execution_plan"]
    assert result.checkpoint_artifact()


@pytest.mark.parametrize(
    ("control", "reason_code"),
    [
        (
            "direct_displacement_control",
            "planar_frame_direct_displacement_control_experimental",
        ),
        ("arc_length", "planar_frame_arc_length_experimental"),
    ],
)
def test_experimental_control_modes_fail_with_stable_reason(
    control: str, reason_code: str
) -> None:
    document = parse_model_ir_v2(_verified_payload(), require_analysis_ready=True)
    result = analyze_planar_frame(document, PlanarFrameConfig(control=control))
    report = validate_planar_frame_result(result)
    assert result.status == "not_run"
    assert result.converged is None
    assert result.result_ir is None
    assert result.unsupported_features[0]["kind"] == "unsupported"
    assert result.unsupported_features[0]["reason_code"] == reason_code
    assert report.contract_pass is False
    assert report.unsupported_reason_codes == (reason_code,)
    assert reason_code in PLANAR_FRAME_UNSUPPORTED_REASON_CODES


def test_legacy_profile_remains_valid_but_is_not_silently_promoted() -> None:
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    document = parse_model_ir_v2(deepcopy(legacy), require_analysis_ready=True)
    assert document.capability_profile == "bounded_planar_frame_alpha"
    with pytest.raises(ValueError, match="capability_profile must be"):
        analyze_planar_frame(document)


def test_status_and_converged_contract_fails_closed_on_tampering() -> None:
    document = parse_model_ir_v2(_verified_payload(), require_analysis_ready=True)
    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(
            load_steps=2,
            maximum_iterations=60,
            residual_tolerance=1.0e-9,
        ),
    )
    assert result.converged is True
    object.__setattr__(result, "converged", False)
    with pytest.raises(ValueError, match="status and converged"):
        validate_planar_frame_result(result)


def test_planar_frame_cli_writes_not_run_contract_for_experimental_mode(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    out_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    model_path.write_text(json.dumps(_verified_payload()), encoding="utf-8")

    exit_code = planar_frame_cli_main(
        [
            str(model_path),
            "--control",
            "arc_length",
            "--out",
            str(out_path),
            "--report-out",
            str(report_path),
        ]
    )

    assert exit_code == 2
    result = json.loads(out_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "not_run"
    assert result["converged"] is None
    assert result["unsupported_features"][0]["reason_code"] == (
        "planar_frame_arc_length_experimental"
    )
    assert report["contract_pass"] is False
    assert report["unsupported_reason_codes"] == [
        "planar_frame_arc_length_experimental"
    ]


def test_planar_frame_console_script_is_packaged() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        'structural-analysis-planar-frame = "structural_analysis.api.planar_frame_cli:main"'
        in pyproject
    )
