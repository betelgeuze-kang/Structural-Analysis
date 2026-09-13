"""Synthetic reporting integrity; not evidence of physical material behavior."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark import planar_frame_backend_process as process


def history(steel=0.0, tensile=0.0, compressive=0.0):
    return {
        "steps": [
            {
                "material_states": [
                    {
                        "material_kind": "steel",
                        "state": {
                            "schema_version": "uniaxial-combined-hardening-state.v1",
                            "accumulated_plastic_strain": steel,
                        },
                    },
                    {
                        "material_kind": "concrete",
                        "state": {
                            "schema_version": "uniaxial-asymmetric-concrete-damage-state.v1",
                            "tensile_damage": tensile,
                            "compressive_damage": compressive,
                        },
                    },
                ]
            }
        ]
    }


def retained(tmp_path, value):
    directory = tmp_path / "slot"
    directory.mkdir(exist_ok=True)
    path = directory / "history.json"
    path.write_bytes(process._bytes(value))
    return {
        "directory": "slot",
        "resource_eligible": True,
        "artifact_contract_pass": True,
        "physical_converged": True,
        "retained_artifacts_intact": True,
        "artifacts": {"history.json": process._file_identity(path)},
    }


def test_zero_is_observed_only_with_retained_verified_history(tmp_path):
    result = process._material_activity(tmp_path, retained(tmp_path, history()))
    assert result["available"] is True
    assert result["steel_plasticity_observed"] is False
    assert result["concrete_damage_observed"] is False
    assert result["material_observation_count"] == 2


def test_nonterminal_material_activity_is_not_lost(tmp_path):
    value = history(0.001, 0.2, 0.3)
    value["steps"].extend(deepcopy(history()["steps"]))
    result = process._material_activity(tmp_path, retained(tmp_path, value))
    assert result["steel_plasticity_observed"] is True
    assert result["concrete_damage_observed"] is True
    assert result["maximum_accumulated_steel_plastic_strain"] == 0.001
    assert result["maximum_concrete_tensile_damage"] == 0.2
    assert result["maximum_concrete_compressive_damage"] == 0.3


@pytest.mark.parametrize(
    "gate",
    [
        "physical_converged",
        "resource_eligible",
        "artifact_contract_pass",
        "retained_artifacts_intact",
    ],
)
def test_failed_or_unverified_path_stays_unknown(tmp_path, gate):
    row = retained(tmp_path, history())
    row[gate] = False
    result = process._material_activity(tmp_path, row)
    assert result["reason"] == "history_unavailable_or_unverified"
    assert result["steel_plasticity_observed"] is None
    assert result["maximum_concrete_tensile_damage"] is None


def test_mutated_bytes_cannot_report_material_activity(tmp_path):
    row = retained(tmp_path, history())
    (tmp_path / "slot/history.json").write_bytes(process._bytes(history(0.1)))
    result = process._material_activity(tmp_path, row)
    assert result["available"] is False
    assert result["maximum_accumulated_steel_plastic_strain"] is None


@pytest.mark.parametrize("value", [True, -1, 1.1, "0.2", None])
def test_invalid_damage_cannot_become_zero_or_positive_evidence(tmp_path, value):
    row = retained(tmp_path, history(0.001, value))
    result = process._material_activity(tmp_path, row)
    assert result["available"] is False
    assert result["steel_plasticity_observed"] is None  # discard partial maxima
    assert result["concrete_damage_observed"] is None


def test_missing_material_kind_is_unavailable_not_undamaged(tmp_path):
    value = history()
    value["steps"][0]["material_states"] = value["steps"][0]["material_states"][:1]
    result = process._material_activity(tmp_path, retained(tmp_path, value))
    assert result["available"] is True
    assert result["steel_plasticity_observed"] is False
    assert result["concrete_damage_observed"] is None


def test_unknown_material_schema_invalidates_partial_summary(tmp_path):
    value = history(0.1)
    value["steps"][0]["material_states"][1]["state"]["schema_version"] = "unknown"
    result = process._material_activity(tmp_path, retained(tmp_path, value))
    assert result["available"] is False
    assert result["steel_plasticity_observed"] is None
