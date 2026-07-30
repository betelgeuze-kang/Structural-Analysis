from __future__ import annotations

import importlib.resources
import json

from jsonschema import Draft202012Validator

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_restart_trace_ir_v1 as trace_v1,
)


def test_restart_trace_ir_public_api_is_additive_unique_and_exact() -> None:
    expected = {name: getattr(trace_v1, name) for name in trace_v1.__all__}
    assert len(trace_v1.__all__) == 19
    assert len(trace_v1.__all__) == len(set(trace_v1.__all__))
    assert all(not name.startswith("_") for name in trace_v1.__all__)
    for name, value in expected.items():
        assert getattr(engine_v2, name) is value
        assert getattr(assembly_backend, name) is value
        assert name in engine_v2.__all__
        assert name in assembly_backend.__all__
    assert len(engine_v2.__all__) == 1263
    assert len(assembly_backend.__all__) == 1071
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))


def test_restart_trace_ir_schema_is_packaged_and_draft_2020_12_valid() -> None:
    schemas = importlib.resources.files("structural_analysis.schemas")
    name = "hip_fgmres_restart_trace_ir_v1.schema.json"
    schema = json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["artifact_kind"]["const"] == (
        "solver_restart_diagnostic_trace"
    )
    claims = schema["$defs"]["claims"]["properties"]
    assert claims["diagnostic_restart_trace_ir_v1_ready"]["const"] is True
    assert claims["solution_ready"]["const"] is False
    assert claims["result_ir_ready"]["const"] is False
    assert claims["result_ir_issuance_authorized"]["const"] is False
    assert claims["promotion_eligible"]["const"] is False
