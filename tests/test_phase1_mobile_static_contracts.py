from __future__ import annotations

import builtins
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_step5_rca_contract_reports_missing_timing_subfield() -> None:
    contract = _load_module(
        "step5_rca_contract_for_tests",
        "implementation/phase1/step5_rca_contract.py",
    )

    report = contract.validate_step5_rca_summary(
        {
            "timing_breakdown_seconds": {
                "compute": 1.0,
                "host_copy": 0.0,
            }
        }
    )

    assert report.contract_pass is False
    assert report.reason_code == "ERR_MISSING_RCA_KEY"
    assert report.missing_fields == ("timing_breakdown_seconds.serialization",)
    assert report.invalid_fields == ()
    assert report.to_dict()["schema_anchor"] == "implementation/phase1/step5_rca_summary.schema.json"


@pytest.mark.parametrize("host_copy_share", [-0.01, 1.01])
def test_step5_rca_contract_rejects_host_copy_share_outside_unit_range(host_copy_share: float) -> None:
    contract = _load_module(
        "step5_rca_contract_for_tests",
        "implementation/phase1/step5_rca_contract.py",
    )

    report = contract.validate_step5_rca_summary(
        {
            "timing_breakdown_seconds": {
                "compute": 1.0,
                "host_copy": 0.0,
                "serialization": 0.25,
            },
            "host_copy_share": host_copy_share,
        }
    )

    assert report.contract_pass is False
    assert report.reason_code == "ERR_INVALID_RCA_VALUE"
    assert report.missing_fields == ()
    assert report.invalid_fields == ("host_copy_share",)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -1.0, "not-a-number"])
def test_step5_rca_contract_rejects_invalid_timing_values(bad_value: object) -> None:
    contract = _load_module(
        "step5_rca_contract_for_tests",
        "implementation/phase1/step5_rca_contract.py",
    )

    report = contract.validate_step5_rca_summary(
        {
            "timing_breakdown_seconds": {
                "compute": 1.0,
                "host_copy": bad_value,
                "serialization": 0.25,
            }
        }
    )

    assert report.contract_pass is False
    assert report.reason_code == "ERR_INVALID_RCA_VALUE"
    assert report.missing_fields == ()
    assert report.invalid_fields == ("timing_breakdown_seconds.host_copy",)


def test_lf_to_gnn_smoke_reports_python_fallback_truthfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    smoke = _load_module(
        "lf_to_gnn_e2e_smoke_for_tests",
        "implementation/phase1/lf_to_gnn_e2e_smoke.py",
    )

    real_import = builtins.__import__

    def _blocked_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist=(),
        level: int = 0,
    ):
        if name == "gnn_residual_model":
            raise ImportError("forced fallback for mobile/static contract test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    nodes_csv = _write_text(
        tmp_path / "ulf_nodes.csv",
        "node_id,ux,uy,uz,f_norm\nN1,0.0,0.0,0.0,100.0\nN2,0.1,0.0,0.0,50.0\n",
    )
    edges_csv = _write_text(
        tmp_path / "ulf_edges.csv",
        "from,to\nN1,N2\n",
    )
    meta_json = _write_text(
        tmp_path / "ulf_meta.json",
        json.dumps({"unit_system": "m-kN", "solver": "lf_static"}),
    )

    report = smoke.run(
        nodes_csv,
        edges_csv,
        meta_json,
        batch_size=2,
        gain=0.001,
        target_accuracy_pct=99.9,
    )

    assert report["pass"] is False
    assert report["reason_code"] == "ERR_RESIDUAL_ACCURACY"
    assert report["standard_reason_code"] == "ERR_LF_GNN_ACCURACY_BELOW_TARGET"
    assert report["claim_boundary"] == "residual_correction_assist_not_solver_truth"
    assert report["inference"]["fallback_used"] is True
    assert report["inference"]["fallback_reason"] == "model_or_import_failure"
    assert report["inference"]["model_module"] == "python_fallback"
    assert report["contract"]["mobile_static_contract_ref"].endswith("#a1-lf---gnn-interface-contract")
