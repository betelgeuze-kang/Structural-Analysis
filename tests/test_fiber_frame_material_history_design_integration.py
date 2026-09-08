"""Two actual RC analyses exercise the complete opt-in material design screen.

The declared damage threshold is a synthetic caller screen, not an engineering
acceptance criterion. Timings from this test are not performance evidence.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.fiber_frame_design_cli import (
    write_fiber_frame_design_bundle,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


ROOT = Path(__file__).resolve().parents[1]


def _encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def _source_identity():
    names = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "src/structural_analysis"], text=True
    ).splitlines()
    identities = {}
    for name in names:
        assert ".env" not in Path(name).name
        identities[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return canonical_hash(identities)


@pytest.fixture(scope="module")
def actual_material_comparison():
    directory = Path(tempfile.mkdtemp(prefix="structural-material-design-integration-"))
    print(f"Actual material design artifacts: {directory}", flush=True)
    model_path = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
    (directory / "baseline-input.json").write_bytes(model_path.read_bytes())
    baseline = load_neutral_json(model_path)
    source_identity = _source_identity()
    original = public_api.analyze_public_rc_fiber_frame
    calls = []

    def observed(model, config):
        result = original(model, config)
        row = {
            "canonical_model_checksum": model.canonical_model_checksum,
            "input_checksum": model.input_checksum,
            "result": result,
            "public_bytes": _encoded(result.to_dict()),
            "checkpoint_bytes": result.checkpoint_artifact(),
        }
        index = len(calls)
        (directory / f"public-{index}.json").write_bytes(row["public_bytes"])
        (directory / f"checkpoint-{index}.json").write_bytes(row["checkpoint_bytes"])
        calls.append(row)
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(public_api, "analyze_public_rc_fiber_frame", observed)
        comparison = design.compare_public_rc_fiber_frame_designs(
            baseline,
            (
                design.FiberFrameDesignCandidate(
                    "wider", (design.FiberFrameSectionChange("RC1", width_m=0.5),)
                ),
            ),
            public_api.PublicRCFiberFrameConfig(load_steps=4),
            prices=design.FiberFrameMaterialPrices(
                100.0, 1.0, "KRW", "2026-09-09", "synthetic test prices; not a quote"
            ),
            terminal_limits=design.FiberFrameTerminalLimits(1.0, 1.0),
            history_limits=design.FiberFrameHistoryLimits(1.0, 1.0),
            material_history_limits=design.FiberFrameMaterialHistoryLimits(
                maximum_steel_accumulated_plastic_strain=0.0,
                maximum_concrete_tensile_damage=0.95,
                maximum_concrete_compressive_damage=0.0,
            ),
            source_revision=source_identity,
        )
    payload = comparison.to_dict()
    (directory / "comparison.json").write_bytes(_encoded(payload))
    manifest = write_fiber_frame_design_bundle(comparison, directory / "bundle")
    assert _source_identity() == source_identity
    return SimpleNamespace(
        directory=directory,
        comparison=comparison,
        payload=payload,
        calls=calls,
        manifest=manifest,
    )


def test_actual_material_screen_uses_two_full_reference_analyses(
    actual_material_comparison,
):
    fixture = actual_material_comparison
    assert (
        len(fixture.calls)
        == fixture.payload["runtime"]["reference_analysis_request_count"]
        == 2
    )
    assert fixture.payload["schema_version"] == "public-rc-fiber-design-comparison.v3"
    assert fixture.payload["status"] == "ready"
    for call, row in zip(fixture.calls, fixture.payload["rows"], strict=True):
        assert row["full_reference_verification_pass"] is True
        assert row["full_history_verification_pass"] is True
        assert row["full_material_history_verification_pass"] is True
        assert row["terminal_limit_status"] == row["history_limit_status"] == "pass"
        assert _encoded(call["result"].to_dict()) == call["public_bytes"]
        assert call["result"].checkpoint_artifact() == call["checkpoint_bytes"]
        assert row["quantities"] is not None and row["material_estimate"] is not None


def test_actual_declared_damage_screen_changes_eligible_selection(
    actual_material_comparison,
):
    payload = actual_material_comparison.payload
    baseline, wider = payload["rows"]
    assert baseline["material_history_limit_status"] == "fail"
    assert wider["material_history_limit_status"] == "pass"
    metric = "history_maximum_concrete_tensile_damage"
    assert baseline["performance"][metric] > 0.95 >= wider["performance"][metric]
    assert baseline["material_estimate"]["total"] < wider["material_estimate"]["total"]
    assert payload["selection"]["candidate_id"] == "wider"
    assert payload["selection"]["eligible_count"] == 1
    assert baseline["violated_material_history_limits"] == [metric]


def test_actual_material_maxima_bind_all_original_accepted_states(
    actual_material_comparison,
):
    fields = {
        "history_maximum_steel_accumulated_plastic_strain": (
            "steel",
            "accumulated_plastic_strain",
        ),
        "history_maximum_concrete_tensile_damage": ("concrete", "tensile_damage"),
        "history_maximum_concrete_compressive_damage": (
            "concrete",
            "compressive_damage",
        ),
    }
    for row in actual_material_comparison.payload["rows"]:
        companion = row["constitutive_history"]
        assert companion["accepted_epoch_count"] == 4
        assert [state["epoch"] for state in companion["states"]] == list(range(5))
        assert (
            companion["bindings"]["source_result_hash"] == row["result"]["result_hash"]
        )
        assert (
            companion["bindings"]["response_history_report_hash"]
            == row["response_history"]["report_hash"]
        )
        for metric, (material, field) in fields.items():
            maximum = max(
                state["materials"][material]["fields"][field]["maximum"]
                for state in companion["states"][1:]
            )
            assert row["performance"][metric] == maximum
        assert all(value is False for value in companion["claim_boundary"].values())
        assert (
            row["performance"]["history_maximum_steel_accumulated_plastic_strain"]
            == 0.0
        )


def test_actual_bundle_preserves_complete_material_payload_without_new_analysis(
    actual_material_comparison,
):
    fixture = actual_material_comparison
    manifest = json.loads(fixture.manifest.read_bytes())
    raw = (fixture.manifest.parent / manifest["report_file"]).read_bytes()
    assert manifest["report_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert manifest["report_byte_length"] == len(raw)
    assert json.loads(raw) == fixture.payload
    assert len(fixture.calls) == 2
    assert all(
        row["constitutive_history"] is not None for row in json.loads(raw)["rows"]
    )
