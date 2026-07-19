"""Contract tests for authored MIDAS MGT static-load assembly."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


PHASE1 = Path(__file__).resolve().parents[1] / "implementation" / "phase1"
sys.path.insert(0, str(PHASE1))

from mgt_semantic_load_assembly import (  # noqa: E402
    MgtSemanticLoadContractError,
    assemble_mgt_semantic_reference_load,
)


def _topology() -> dict[str, np.ndarray]:
    return {
        "node_id": np.asarray([10, 20, 30, 40], dtype=np.int64),
        "node_xyz": np.asarray(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [2.0, 3.0, 0.0],
                [0.0, 3.0, 0.0],
            ],
            dtype=np.float64,
        ),
        "elem_id": np.asarray([101], dtype=np.int64),
        "elem_type_code": np.asarray([2], dtype=np.int32),
        "conn_ptr": np.asarray([0, 4], dtype=np.int64),
        "conn_idx": np.asarray([0, 1, 2, 3], dtype=np.int64),
    }


def _pressure_row(*, load_case: str = "LIVE", projected: str = "NO") -> dict:
    return {
        "element_ids": [101],
        "command": "PRES",
        "element_type": "PLATE",
        "load_type": "FACE",
        "direction": "GZ",
        "direction_vector": [0.0, 0.0, 0.0],
        "projected": projected,
        "uniform_pressure": -5.0,
        "corner_pressures": [0.0, 0.0, 0.0, 0.0],
        "load_case": load_case,
    }


def _payload() -> dict:
    return {
        "model": {
            "units": {"force": "KN", "length": "M"},
            "loads": {
                "static_load_cases": [
                    {"name": "DEAD", "type": "D"},
                    {"name": "LIVE", "type": "L"},
                ],
                "nodal_loads": [
                    {
                        "node_ids": [20],
                        "fx": 2.0,
                        "fy": 0.0,
                        "fz": -4.0,
                        "mx": 1.0,
                        "my": 2.0,
                        "mz": 3.0,
                        "load_case": "LIVE",
                    },
                    {
                        "node_ids": [10],
                        "fx": 0.0,
                        "fy": 1.0,
                        "fz": 0.0,
                        "mx": 0.0,
                        "my": 0.0,
                        "mz": 0.0,
                        "load_case": "DEAD",
                    },
                ],
                "pressure_loads": [_pressure_row()],
                "selfweight": [],
                "load_combinations": [
                    {
                        "name": "SERVICE",
                        "expansion_mode": "linear_combination",
                        "expanded_factor_map": {"DEAD": 1.0, "LIVE": 0.5},
                    },
                    {
                        "name": "ENVELOPE",
                        "expansion_mode": "envelope_union",
                        "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0},
                    },
                ],
            },
        }
    }


def test_live_case_assembles_nodal_and_uniform_global_pressure_in_si() -> None:
    vector, metadata = assemble_mgt_semantic_reference_load(
        model_payload=_payload(),
        load_case="live",
        **_topology(),
    )

    matrix = vector.reshape((-1, 6))
    np.testing.assert_allclose(matrix[:, 2], [-7500.0, -11500.0, -7500.0, -7500.0])
    np.testing.assert_allclose(matrix[1, :], [2000.0, 0.0, -11500.0, 1000.0, 2000.0, 3000.0])
    np.testing.assert_allclose(
        np.sum(matrix[:, :3], axis=0),
        [2000.0, 0.0, -34000.0],
    )
    assert metadata["status"] == "ready"
    assert metadata["contract_pass"] is True
    assert metadata["target_kind"] == "static_load_case"
    assert metadata["target_name"] == "LIVE"
    assert metadata["nodal_load_row_count_consumed"] == 1
    assert metadata["pressure_load_element_count_consumed"] == 1
    assert metadata["pressure_loaded_area_m2"] == pytest.approx(6.0)
    assert metadata["pressure_force_resultant_n"] == [0.0, 0.0, -30000.0]
    assert metadata["resultant_gate_passed"] is True
    assert metadata["actual_mgt_semantic_load_target_consumed"] is True
    assert metadata["production_load_case_claim"] is False
    assert metadata["promotes_g1_closure"] is False


def test_linear_combination_applies_case_factors_without_envelope_promotion() -> None:
    vector, metadata = assemble_mgt_semantic_reference_load(
        model_payload=_payload(),
        load_combination="SERVICE",
        **_topology(),
    )

    matrix = vector.reshape((-1, 6))
    np.testing.assert_allclose(
        np.sum(matrix[:, :3], axis=0),
        [1000.0, 1000.0, -17000.0],
    )
    assert metadata["target_kind"] == "linear_load_combination"
    assert metadata["case_factors"] == {"DEAD": 1.0, "LIVE": 0.5}
    assert metadata["source_mgt_load_combination_consumed"] is True


def test_selected_selfweight_fails_closed_instead_of_using_a_density_proxy() -> None:
    payload = _payload()
    payload["model"]["loads"]["selfweight"] = [
        {"gx": 0.0, "gy": 0.0, "gz": -1.0, "load_case": "DEAD"}
    ]

    with pytest.raises(MgtSemanticLoadContractError) as captured:
        assemble_mgt_semantic_reference_load(
            model_payload=payload,
            load_combination="SERVICE",
            **_topology(),
        )

    assert captured.value.reason_code == "ERR_MGT_SEMANTIC_LOAD_SELFWEIGHT_UNSUPPORTED"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (
            lambda payload: payload["model"]["loads"]["pressure_loads"][0].update(
                {"projected": "YES"}
            ),
            "ERR_MGT_SEMANTIC_LOAD_PROJECTED_PRESSURE_UNSUPPORTED",
        ),
        (
            lambda payload: payload["model"]["loads"]["pressure_loads"][0].update(
                {"corner_pressures": [-5.0, -4.0, -3.0, -2.0]}
            ),
            "ERR_MGT_SEMANTIC_LOAD_NONUNIFORM_PRESSURE_UNSUPPORTED",
        ),
    ],
)
def test_unsupported_pressure_semantics_fail_closed(mutation, reason_code: str) -> None:
    payload = _payload()
    mutation(payload)

    with pytest.raises(MgtSemanticLoadContractError) as captured:
        assemble_mgt_semantic_reference_load(
            model_payload=payload,
            load_case="LIVE",
            **_topology(),
        )

    assert captured.value.reason_code == reason_code


def test_envelope_and_unknown_units_fail_closed() -> None:
    with pytest.raises(MgtSemanticLoadContractError) as envelope:
        assemble_mgt_semantic_reference_load(
            model_payload=_payload(),
            load_combination="ENVELOPE",
            **_topology(),
        )
    assert envelope.value.reason_code == "ERR_MGT_SEMANTIC_LOAD_ENVELOPE_UNSUPPORTED"

    payload = _payload()
    payload["model"]["units"] = {"force": "KIP", "length": "FT"}
    with pytest.raises(MgtSemanticLoadContractError) as units:
        assemble_mgt_semantic_reference_load(
            model_payload=payload,
            load_case="LIVE",
            **_topology(),
        )
    assert units.value.reason_code == "ERR_MGT_SEMANTIC_LOAD_UNIT_UNSUPPORTED"
