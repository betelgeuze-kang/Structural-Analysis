from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import structural_analysis.engine_v2 as engine_v2  # noqa: E402
import structural_analysis.engine_v2.solvers as solvers  # noqa: E402

PUBLIC_NAMES = (
    "CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1",
    "CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1",
    "CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION",
    "CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION",
    "DEFAULT_CPU_FGMRES_COARSE_CONDITION_LIMIT_V1",
    "DEFAULT_CPU_FGMRES_COARSE_DROP_TOLERANCE_V1",
    "MAX_CPU_FGMRES_COARSE_RANK_V1",
    "CpuFgmresCoarseArrayDescriptorV1",
    "CpuFgmresCoarseComplexityReceiptV1",
    "CpuFgmresCoarseSolveComplexityReceiptV1",
    "CpuFgmresFixedRankCoarseError",
    "CpuFgmresFixedRankCoarseResultV1",
    "CpuFgmresFixedRankCoarseSpaceV1",
    "apply_cpu_fgmres_fixed_rank_coarse_v1",
    "build_cpu_fgmres_fixed_rank_coarse_space_v1",
    "solve_cpu_fgmres_fixed_rank_coarse_v1",
    "validate_cpu_fgmres_fixed_rank_coarse_result_v1",
    "validate_cpu_fgmres_fixed_rank_coarse_result_v1_shallow",
    "validate_cpu_fgmres_fixed_rank_coarse_space_v1",
)


def test_public_api_is_identical_at_solver_and_engine_boundaries() -> None:
    for name in PUBLIC_NAMES:
        assert name in solvers.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(solvers, name)
    assert len(PUBLIC_NAMES) == 19


def test_exact_schema_resources_ship_with_the_package() -> None:
    resource_root = files("structural_analysis.schemas")
    expected = {
        "cpu_fgmres_fixed_rank_coarse_space_v1.schema.json": (
            "structural-analysis-cpu-fgmres-fixed-rank-coarse-space.v1"
        ),
        "cpu_fgmres_fixed_rank_coarse_result_v1.schema.json": (
            "structural-analysis-cpu-fgmres-fixed-rank-coarse-result.v1"
        ),
    }
    for name, schema_version in expected.items():
        payload = json.loads(resource_root.joinpath(name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
        assert payload["properties"]["schema_version"]["const"] == schema_version


def test_public_surface_counts_include_the_additive_contract() -> None:
    assert len(engine_v2.__all__) == 1196
    assert len(solvers.__all__) == 66
