from __future__ import annotations

import importlib.resources

import structural_analysis.engine_v2 as engine_v2
from structural_analysis.engine_v2 import assembly_backend, solvers
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_runner_key_lifecycle_v3 as lifecycle_v3,
)


def test_runner_key_lifecycle_v3_public_surface_is_unique_and_identity_preserving() -> (
    None
):
    assert len(lifecycle_v3.__all__) == 30
    assert len(lifecycle_v3.__all__) == len(set(lifecycle_v3.__all__))
    assert len(engine_v2.__all__) == 1263
    assert len(assembly_backend.__all__) == 1071
    assert len(solvers.__all__) == 66
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))
    assert len(solvers.__all__) == len(set(solvers.__all__))

    for name in lifecycle_v3.__all__:
        assert getattr(engine_v2, name) is getattr(assembly_backend, name)
        assert getattr(assembly_backend, name) is getattr(lifecycle_v3, name)


def test_runner_key_lifecycle_v3_schema_is_packaged_and_signing_is_not_public() -> None:
    schema = (
        importlib.resources.files("structural_analysis.schemas")
        .joinpath("hip_fgmres_external_runner_key_lifecycle_v3.schema.json")
        .read_text(encoding="utf-8")
    )

    assert "external-runner-key-lifecycle.v3" in schema
    assert "phase0_external_gfx1100_runner_key_enrollment_activation_v3" in schema
    assert not any(name.startswith("sign_") for name in lifecycle_v3.__all__)
