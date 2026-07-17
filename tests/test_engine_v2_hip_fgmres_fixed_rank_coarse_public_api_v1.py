from __future__ import annotations

import importlib.resources
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import structural_analysis.engine_v2 as engine_v2  # noqa: E402
from structural_analysis.engine_v2 import assembly_backend, solvers  # noqa: E402
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_context_v1 as coarse_context_v1,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_plan_v1 as coarse_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_rtc_v1 as coarse_rtc_v1,
)


def test_fixed_rank_coarse_public_surface_is_unique_and_identity_preserving() -> None:
    assert len(coarse_plan_v1.__all__) == 16
    assert len(coarse_rtc_v1.__all__) == 8
    assert len(coarse_context_v1.__all__) == 20
    assert len(engine_v2.__all__) == 1196
    assert len(assembly_backend.__all__) == 1004
    assert len(solvers.__all__) == 66
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))
    assert len(solvers.__all__) == len(set(solvers.__all__))

    for module in (coarse_plan_v1, coarse_rtc_v1, coarse_context_v1):
        assert len(module.__all__) == len(set(module.__all__))
        assert all(not name.startswith("_") for name in module.__all__)
        for name in module.__all__:
            assert getattr(engine_v2, name) is getattr(assembly_backend, name)
            assert getattr(assembly_backend, name) is getattr(module, name)


def test_fixed_rank_coarse_schema_and_kernel_source_are_packaged() -> None:
    schemas = tuple(
        importlib.resources.files("structural_analysis.schemas")
        .joinpath(name)
        .read_text(encoding="utf-8")
        for name in (
            "hip_fgmres_fixed_rank_coarse_plan_v1.schema.json",
            "hip_fgmres_fixed_rank_coarse_context_v1.schema.json",
            "hip_fgmres_fixed_rank_coarse_application_v1.schema.json",
        )
    )
    kernel = (
        importlib.resources.files(
            "structural_analysis.engine_v2.assembly_backend.kernels"
        )
        .joinpath("engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp")
        .read_text(encoding="utf-8")
    )

    assert "hip-fgmres-fixed-rank-coarse-plan.v1" in schemas[0]
    assert "hip-fgmres-fixed-rank-coarse-context.v1" in schemas[1]
    assert "hip-fgmres-fixed-rank-coarse-application.v1" in schemas[2]
    for symbol in coarse_plan_v1.HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1:
        assert symbol in kernel
