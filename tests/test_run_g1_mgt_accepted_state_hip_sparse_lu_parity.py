from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    build_hip_sparse_lu_apply_reference,
)


def _load_runner():
    path = ROOT / "scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py"
    spec = importlib.util.spec_from_file_location("g1_mgt_sparse_lu_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runner import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_and_claim_boundary_are_fail_closed() -> None:
    runner = _load_runner()
    schema = json.loads((ROOT / runner.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    assert schema["properties"]["accepted_state"]["properties"]["load_factor"] == {"const": 1.0}
    assert schema["properties"]["accepted_state"]["properties"]["equation_count"] == {"const": 70560}
    claims = schema["properties"]["claims"]["properties"]
    assert claims["actual_mgt_70560_factor_apply"] == {"const": True}
    assert claims["production_current_tangent_fgmres"] == {"const": False}
    assert claims["independent_gfx1100"] == {"const": False}
    assert claims["g1_closure"] == {"const": False}


def test_device_telemetry_counts_fixture_residency() -> None:
    runner = _load_runner()
    reference = build_hip_sparse_lu_apply_reference()

    telemetry = runner._device_telemetry(reference)

    assert telemetry["d2h_bytes"] == reference.fixture.dimension * 8
    assert telemetry["mid_apply_d2h_bytes"] == 0
    assert telemetry["h2d_bytes"] > telemetry["d2h_bytes"]
    assert telemetry["tracked_peak_device_allocation_bytes"] == (
        telemetry["h2d_bytes"] + 4 * telemetry["d2h_bytes"]
    )


def test_solution_artifact_is_canonical_little_endian(tmp_path: Path) -> None:
    runner = _load_runner()
    solution = np.linspace(-1.0, 1.0, runner.EQUATION_COUNT, dtype=np.float64)
    path = tmp_path / "solution.f64le"

    manifest, raw = runner._solution_artifact(
        repo_root=tmp_path,
        solution_out=path,
        solution=solution,
    )

    assert manifest["dtype"] == "<f8"
    assert manifest["shape"] == [runner.EQUATION_COUNT]
    assert manifest["byte_length"] == runner.SOLUTION_BYTE_LENGTH
    assert len(raw) == runner.SOLUTION_BYTE_LENGTH
    assert np.array_equal(np.frombuffer(raw, dtype="<f8"), solution)


def test_check_fails_closed_when_receipt_is_missing(tmp_path: Path) -> None:
    runner = _load_runner()

    passed, reason = runner.check_receipt(
        repo_root=tmp_path,
        out_path=Path("missing.json"),
    )

    assert passed is False
    assert reason == "g1_mgt_accepted_state_hip_sparse_lu_receipt_missing"


def test_runner_declares_accepted_state_and_no_integrated_fgmres() -> None:
    runner = _load_runner()
    source = Path(runner.__file__).read_text(encoding="utf-8")

    for token in (
        "full_load_checkpoint_accepted_free_displacements",
        "negative_physical_residual_at_accepted_state",
        "current_tangent_operator_and_preconditioner_not_integrated_in_one_device_fgmres",
        "factor_not_persisted_across_krylov_iterations",
        "independent_gfx1100_run_not_available",
    ):
        assert token in source
