from __future__ import annotations

from importlib import resources
import json

from structural_analysis.results import (
    VIEWER_MODEL_IDENTITY_POLICY,
    VIEWER_SCHEMA_VERSION,
    ViewerPayloadValidationError,
    validate_linear_static_viewer_payload,
)
from structural_analysis.results import __all__ as result_exports


_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _payload() -> dict[str, object]:
    zero_displacement = {
        "UX": 0.0,
        "UY": 0.0,
        "UZ": 0.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
    }
    zero_force = {
        "FX": 0.0,
        "FY": 0.0,
        "FZ": 0.0,
        "MX": 0.0,
        "MY": 0.0,
        "MZ": 0.0,
    }
    return {
        "schema_version": VIEWER_SCHEMA_VERSION,
        "source": "authoritative_solver_result",
        "solver_path_id": "authoritative_cpu_linear_fea_3d_v1",
        "analysis_fidelity": "cpu_reference_linear_fea",
        "reaction_definition": "constrained_dof_internal_minus_external_force",
        "equilibrium_residual_definition": (
            "free_dof_internal_minus_external_force; constrained entries are zero"
        ),
        "model_identity": {
            "identity_policy": VIEWER_MODEL_IDENTITY_POLICY,
            "source_input_checksum": _HASH_A,
            "canonical_model_checksum": _HASH_B,
            "analysis_input_snapshot": "detached_canonical_model_v1",
        },
        "nodes": [
            {
                "id": "1",
                "coordinates": [0.0, 0.0, 0.0],
                "displacement": dict(zero_displacement),
                "reaction": dict(zero_force),
                "equilibrium_residual": dict(zero_force),
            },
            {
                "id": "2",
                "coordinates": [1.0, 0.0, 0.0],
                "displacement": dict(zero_displacement),
                "reaction": dict(zero_force),
                "equilibrium_residual": dict(zero_force),
            },
        ],
        "elements": [
            {
                "id": "1",
                "type": "truss",
                "nodes": ["1", "2"],
                "axial_force": 0.0,
                "elongation": 0.0,
                "local_end_forces": {"FX_I": 0.0, "FX_J": 0.0},
            }
        ],
    }


def test_results_package_exports_only_the_stable_viewer_validation_surface() -> None:
    expected = {
        "VIEWER_MODEL_IDENTITY_POLICY",
        "VIEWER_SCHEMA_VERSION",
        "ViewerPayloadValidationError",
        "validate_linear_static_viewer_payload",
    }
    assert expected <= set(result_exports)
    assert "bind_viewer_model_identity" not in result_exports
    assert "build_linear_static_viewer_payload" not in result_exports
    assert issubclass(ViewerPayloadValidationError, ValueError)
    assert validate_linear_static_viewer_payload(_payload()) == _payload()


def test_viewer_schema_is_available_as_an_installed_package_resource() -> None:
    schema_resource = resources.files("structural_analysis").joinpath(
        "schemas",
        "viewer_payload.schema.json",
    )
    assert schema_resource.is_file()
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("/viewer_payload.schema.json")
    assert schema["properties"]["schema_version"]["const"] == (
        VIEWER_SCHEMA_VERSION
    )
    assert schema["$defs"]["modelIdentity"]["properties"][
        "identity_policy"
    ]["const"] == VIEWER_MODEL_IDENTITY_POLICY
