from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_planar_workbench_case.py"
spec = importlib.util.spec_from_file_location("build_planar_workbench_case", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_projection_uses_only_explicit_result_values(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    result = tmp_path / "result.json"
    report = tmp_path / "report.json"
    _write(
        model,
        {
            "capability_profile": module.PROFILE,
            "nodes": [{"id": "N1"}, {"id": "N2"}],
            "elements": [{"id": "E1"}],
        },
    )
    _write(
        result,
        {
            "profile": module.PROFILE,
            "status": "converged",
            "converged": True,
            "result_hash": "sha256:" + "1" * 64,
            "result_ir": {
                "solver_id": "solver.v1",
                "configuration": {
                    "scaled_residual_tolerance": 1e-9,
                    "equation_scaling": {
                        "reference_force_n": 10.0,
                        "characteristic_length_m": 4.0,
                    },
                },
                "metrics": {
                    "terminal_solved_load_factor": 1.0,
                    "dimensionless_scaled_residual_linf": 2e-10,
                    "raw_translational_residual_linf_n": 2e-9,
                    "raw_rotational_residual_linf_nm": 3e-9,
                },
                "contract_bindings": {
                    "bounded_planar_execution_plan": {
                        "physical_dof_count": 12,
                        "engine_equation_scaling_hash": "sha256:" + "2" * 64,
                    }
                },
                "convergence_history": [
                    {
                        "load_step": 1,
                        "iteration": 0,
                        "scaled_residual_norm": 0.1,
                        "relative_increment": 0.02,
                        "line_search_alpha": 1.0,
                    },
                    {
                        "load_step": 2,
                        "iteration": 0,
                        "scaled_residual_norm": 2e-10,
                        "relative_increment": 1e-11,
                        "line_search_alpha": 1.0,
                    },
                ],
            },
        },
    )
    _write(
        report,
        {
            "artifact_contract_pass": True,
            "execution_contract_pass": True,
            "diagnostic_authority": True,
            "numerical_result_authority": True,
            "engineering_result_authority": True,
        },
    )

    case = module.build_workbench_case(
        model_path=model,
        result_path=result,
        report_path=report,
        source_commit_sha="a" * 40,
        engine_version="structural-analysis@0.3.0",
        generated_at="2026-08-03T00:00:00Z",
    )

    assert case["schemaVersion"] == "workbench-case.v2"
    assert case["capability_profile"] == module.PROFILE
    assert case["model"]["nodeCount"] == {"status": "available", "value": 2}
    assert case["model"]["elementCount"] == {"status": "available", "value": 1}
    assert case["model"]["dofCount"] == {"status": "available", "value": 12}
    assert case["analysis"]["status"] == "converged"
    assert case["analysis"]["converged"] is True
    assert case["analysis"]["iterationCount"] == {"status": "available", "value": 2}
    assert [row["iteration"]["value"] for row in case["residualHistory"]] == [0, 1]
    assert [row["source"]["iteration"] for row in case["residualHistory"]] == [0, 0]
    assert case["analysis"]["finalRelativeIncrement"] == {
        "status": "available",
        "value": 1e-11,
    }
    scaling = case["analysis"]["equation_scaling_6dof"]
    assert scaling["reference_force"] == {"status": "available", "value": 10.0}
    assert scaling["translation_increment_norm"] == {"status": "unavailable"}
    assert scaling["rotation_increment_norm"] == {"status": "unavailable"}
    assert scaling["scaling_hash"] == {
        "status": "available",
        "value": "sha256:" + "2" * 64,
    }


def test_projection_preserves_missing_numerics_as_unavailable(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    result = tmp_path / "result.json"
    report = tmp_path / "report.json"
    _write(model, {"capability_profile": module.PROFILE})
    _write(
        result,
        {
            "profile": module.PROFILE,
            "status": "not_run",
            "converged": None,
            "result_hash": "sha256:" + "3" * 64,
            "result_ir": {},
        },
    )
    _write(
        report,
        {
            "artifact_contract_pass": True,
            "execution_contract_pass": True,
        },
    )

    case = module.build_workbench_case(
        model_path=model,
        result_path=result,
        report_path=report,
        source_commit_sha="b" * 40,
        engine_version="structural-analysis@0.3.0",
        generated_at="2026-08-03T00:00:00Z",
    )

    assert case["model"]["nodeCount"] == {"status": "unavailable"}
    assert case["analysis"]["loadScale"] == {"status": "unavailable"}
    assert case["analysis"]["converged"] == {"status": "unavailable"}
    assert case["analysis"]["equation_scaling_6dof"]["scaled_residual_norm"] == {
        "status": "unavailable"
    }
