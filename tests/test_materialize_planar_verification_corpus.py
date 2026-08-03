from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from structural_analysis.api.planar_frame import PlanarFrameConfig, analyze_planar_frame
from structural_analysis.model_ir import parse_model_ir_v2, validate_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize_planar_verification_corpus.py"
spec = importlib.util.spec_from_file_location(
    "materialize_planar_verification_corpus",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_all_declared_cases_are_connected_and_model_ir_valid() -> None:
    for case_id, (node_count, member_count) in module.CASE_SIZES.items():
        payload = module.build_case(case_id)
        assert payload["capability_profile"] == module.PROFILE
        assert len(payload["nodes"]) == node_count
        assert len(payload["elements"]) == member_count
        report = validate_model_ir_v2(payload)
        assert report.schema_valid is True, (case_id, report.blockers)
        assert report.semantics_valid is True, (case_id, report.blockers)
        assert report.analysis_ready is True, (case_id, report.blockers)
        document = parse_model_ir_v2(payload, require_analysis_ready=True)
        assert document.capability_profile == module.PROFILE


def test_medium_seed_executes_through_public_sparse_path() -> None:
    document = parse_model_ir_v2(module.build_case("M1"), require_analysis_ready=True)
    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(
            load_steps=1,
            maximum_iterations=30,
            residual_tolerance=1.0e-8,
            increment_tolerance_m=1.0e-10,
            matrix_backend="scipy_sparse_spsolve_cpu",
        ),
    )
    assert result.status == "converged"
    assert result.converged is True
    assert result.result_ir is not None
    assert result.result_ir["engineering_result_ir"] is not None
    assert result.checkpoint_artifact()


def test_materializer_writes_exact_declared_counts(tmp_path: Path) -> None:
    assert module.main([
        "--case",
        "M2",
        "--case",
        "L2",
        "--out-dir",
        str(tmp_path),
    ]) == 0
    receipt = module.json.loads(
        (tmp_path / "materialization-receipt.json").read_text(encoding="utf-8")
    )
    rows = {row["case_id"]: row for row in receipt["artifacts"]}
    assert rows["M2"]["node_count"] == 36
    assert rows["M2"]["member_count"] == 56
    assert rows["L2"]["node_count"] == 126
    assert rows["L2"]["member_count"] == 220
