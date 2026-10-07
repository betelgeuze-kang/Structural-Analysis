from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/prepare_he_ref_comparison.py"
spec = importlib.util.spec_from_file_location("prepare_he", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def rows(points):
    return [
        {"source_row": i + 5, "deflection_mm_xml": str(x), "load_kN_xml": str(y)}
        for i, (x, y) in enumerate(points)
    ]


def test_preserves_reversals_and_selects_first_crossing():
    values = rows([(0, 0), (2, 20), (0, 4), (2, 40)])
    original = [dict(r) for r in values]
    result = module.checkpoint(values, "1")
    assert result["upward_crossing_count"] == 2
    assert result["selected"]["source_rows"] == [5, 6]
    assert Decimal(result["selected"]["load_channel_kN"]) == 10
    assert Decimal(result["all_crossings"][1]["load_channel_kN"]) == 22
    assert values == original


def test_exact_endpoint_is_counted_once_and_plateau_ignored():
    values = rows([(0, 0), (1, 10), (1, 12), (2, 20)])
    assert len(module.crossings(values, Decimal("1"))) == 1
    assert module.checkpoint(values, "0")["selected"] is None


def test_does_not_extrapolate_or_sort():
    assert module.checkpoint(rows([(2, 20), (0, 0)]), "1")["selected"] is None
    result = module.checkpoint(rows([(0, 0), (1, 10)]), "2")
    assert result["status"] == "outside_observed_upward_crossings"


def test_rejects_unverified_measurement_bytes(tmp_path):
    file = tmp_path / "rows.jsonl"
    file.write_text("{}\n")
    with pytest.raises(ValueError, match="measurement_identity_mismatch"):
        module.prepare(file, tmp_path / "absent-plan.json")


@pytest.fixture
def synthetic_inputs(tmp_path, monkeypatch):
    """Synthetic unit fixture; production still requires the real pinned digest."""
    measurements = tmp_path / "measurements.jsonl"
    data = rows((Decimal(i) / 100, Decimal(i) / 10) for i in range(2632))
    raw = b"".join((json.dumps(row) + "\n").encode() for row in data)
    measurements.write_bytes(raw)
    monkeypatch.setattr(module, "MEASUREMENT_SHA256", hashlib.sha256(raw).hexdigest())
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "status": "HOLD",
                "solver_dispatch_authorized": False,
                "checkpoint_deflections_mm": ["0.05", "0.15", "30"],
                "early_secant_interval_mm": ["0.05", "0.15"],
            }
        )
    )
    return measurements, plan


def test_successful_prepare_retains_hold_and_source_bindings(synthetic_inputs):
    measurements, plan = synthetic_inputs
    result = module.prepare(measurements, plan)
    assert result["status"] == "HOLD"
    assert result["solver_run_count"] == 0
    assert result["physical_validation_claim"] is False
    assert result["measurement_pair_count"] == 2632
    assert (
        result["measurement_sha256"]
        == hashlib.sha256(measurements.read_bytes()).hexdigest()
    )
    assert result["plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert Decimal(result["early_secant_channel_kN_per_mm"]) == 10
    assert result["checkpoints"][0]["selected"]["source_rows"] == [9, 10]
    assert result["checkpoints"][-1]["selected"] is None


@pytest.mark.parametrize(
    "change", [{"status": "READY"}, {"solver_dispatch_authorized": True}]
)
def test_rejects_nonheld_or_authorized_plan(synthetic_inputs, change):
    measurements, plan = synthetic_inputs
    payload = json.loads(plan.read_text())
    payload.update(change)
    plan.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="this_tool_only_prepares_held_comparisons"):
        module.prepare(measurements, plan)


def test_cli_exclusively_creates_output(synthetic_inputs, tmp_path, monkeypatch):
    measurements, plan = synthetic_inputs
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--measurements",
            str(measurements),
            "--plan",
            str(plan),
            "--output",
            str(output),
        ],
    )
    module.main()
    original = output.read_bytes()
    assert json.loads(original)["status"] == "HOLD"
    with pytest.raises(FileExistsError):
        module.main()
    assert output.read_bytes() == original
