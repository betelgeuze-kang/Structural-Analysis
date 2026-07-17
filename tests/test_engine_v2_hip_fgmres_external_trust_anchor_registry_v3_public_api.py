from __future__ import annotations

import importlib.resources
import json

from jsonschema import Draft202012Validator

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_trust_anchor_registry_v3 as registry_v3,
)


def test_registry_v3_public_api_is_additive_unique_and_exact() -> None:
    expected = {name: getattr(registry_v3, name) for name in registry_v3.__all__}

    assert len(registry_v3.__all__) == 18
    assert len(registry_v3.__all__) == len(set(registry_v3.__all__))
    assert all(not name.startswith("_") for name in registry_v3.__all__)
    for name, value in expected.items():
        assert getattr(engine_v2, name) is value
        assert getattr(assembly_backend, name) is value
        assert name in engine_v2.__all__
        assert name in assembly_backend.__all__
    assert len(engine_v2.__all__) == 1152
    assert len(assembly_backend.__all__) == 960
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))


def test_registry_v3_schema_is_packaged_strict_and_non_promoting() -> None:
    schemas = importlib.resources.files("structural_analysis.schemas")
    name = "hip_fgmres_external_trust_anchor_registry_v3.schema.json"
    schema = json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"].endswith(
        "trust-anchor-registry.v3"
    )
    assert schema["properties"]["promotion_eligible"]["const"] is False
    genesis = schema["$defs"]["genesis"]["properties"]
    assert genesis["reviewer_authority_count"]["const"] == 3
    assert genesis["activation_endorsement_count"]["const"] == 3
    assert genesis["enrolled_runner_key_count"]["const"] == 0
    assert genesis["active_runner_key_count"]["const"] == 0
    claims = schema["$defs"]["claims"]["properties"]
    assert claims["package_registry_v3_activation_verified"]["const"] is False
    assert claims["runner_key_activation_verified"]["const"] is False
    assert claims["signed_trace_binding_verified"]["const"] is False
    assert claims["actual_external_gfx1100_verified"]["const"] is False
