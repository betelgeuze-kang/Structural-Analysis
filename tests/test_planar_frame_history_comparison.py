"""Pure synthetic history comparisons; no solver/replay or physical authority."""

from copy import deepcopy
import json
import math

import pytest

from structural_analysis.benchmark.planar_frame_backend_comparison import SI_ROWS
from structural_analysis.benchmark.planar_frame_history_comparison import (
    HISTORY_CLAIM_BOUNDARY,
    HISTORY_GROUPS,
    compare_planar_frame_histories,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _hash(value):
    return canonical_hash({"synthetic": value})


def _seal(value):
    value["history_hash"] = canonical_hash(
        {key: item for key, item in value.items() if key != "history_hash"}
    )
    return value


def _materials(epoch):
    return [
        {
            "member_id": "M1",
            "integration_point_index": 0,
            "fiber_index": index,
            "fiber_id": f"F{index}",
            "material_kind": kind,
            "state": {
                "schema_version": f"synthetic-{kind}-state.v1",
                "strain": float(epoch) / 1000,
                "stress_mpa": float(epoch),
                "step_index": epoch,
                "yielded": False,
                "optional": None,
            },
        }
        for index, kind in enumerate(("steel", "concrete"))
    ]


@pytest.fixture
def history():
    root_hash = _hash("epoch0")
    steps = []
    parent = root_hash
    for epoch in (1, 2):
        state_hash = _hash(f"epoch{epoch}")
        steps.append(
            {
                "epoch": epoch,
                "step_index": epoch,
                "load_factor": epoch / 2,
                "parent_state_hash": parent,
                "state_hash": state_hash,
                "si_rows": {
                    "node_displacements": [
                        {"node_id": "N0", "UX_m": 0.0, "UY_m": 0.0, "RZ_rad": 0.0},
                        {
                            "node_id": "N1",
                            "UX_m": float(epoch),
                            "UY_m": 0.0,
                            "RZ_rad": 0.0,
                        },
                    ],
                    "support_reactions": [
                        {
                            "node_id": "N0",
                            "dof": "UY",
                            "unit": "N",
                            "value_si": float(epoch),
                        }
                    ],
                    "member_end_forces": [
                        {"member_id": "M1", "local_end_i": {"FX_N": float(epoch)}}
                    ],
                    "section_results": [
                        {
                            "member_id": "M1",
                            "integration_point_index": 0,
                            "axial_force_N": float(epoch),
                        }
                    ],
                    "fiber_results": [
                        {"member_id": "M1", "fiber_index": 0, "strain": float(epoch)}
                    ],
                },
                "material_states": _materials(epoch),
            }
        )
        parent = state_hash
    return _seal(
        {
            "schema_version": "planar-frame-accepted-history.v1",
            "source_result_hash": _hash("source"),
            "model_identity": {
                key: _hash(key)
                for key in (
                    "model_ir_content_hash",
                    "model_ir_semantic_hash",
                    "model_ir_provenance_hash",
                    "canonical_model_checksum",
                )
            },
            "configuration": {
                "control": "load_control",
                "load_steps": 2,
                "residual_tolerance": 1e-10,
                "increment_tolerance_m": 1e-12,
                "maximum_iterations": 40,
                "matrix_backend": "numpy_linalg_solve_dense",
            },
            "checkpoint_identity": {
                "available": True,
                "storage_profile": "canonical-signed-zero-preserving-utf8-json.v1",
                "chain_hash": _hash("chain"),
                "artifact_hash": _hash("artifact"),
                "artifact_byte_length": 1234,
                "root_state_hash": root_hash,
                "terminal_state_hash": parent,
                "terminal_epoch": 2,
                "terminal_load_factor": 1.0,
                "complete_ancestry_included": True,
                "prefix_replay_required": True,
            },
            "root": {
                "epoch": 0,
                "step_index": 0,
                "load_factor": 0.0,
                "state_hash": root_hash,
                "global_displacements": [0.0] * 6,
                "material_states": _materials(0),
            },
            "steps": steps,
            "claim_boundary": deepcopy(HISTORY_CLAIM_BOUNDARY),
        }
    )


@pytest.fixture
def tolerances():
    return {name: {"absolute": 0.0, "relative": 0.0} for name in HISTORY_GROUPS}


def _compare(left, right, tolerances):
    return compare_planar_frame_histories(left, right, tolerances=tolerances)


def test_complete_history_compares_genesis_and_every_accepted_step(history, tolerances):
    before = deepcopy(history)
    report = _compare(history, deepcopy(history), tolerances)
    assert report["comparison_available"] is True
    assert report["full_history_match"] is True
    assert report["full_history_float_comparison_performed"] is True
    assert report["root_comparison"] == {
        "match": True,
        "node_displacements_match": True,
        "material_states_match": True,
    }
    assert report["step_counts"] == {"left": 2, "right": 2, "compared": 2}
    assert all(row["match"] for row in report["step_comparisons"])
    assert report["groups"]["node_displacements"]["float_leaf_count"] == 18
    assert report["groups"]["material_states"]["float_leaf_count"] == 12
    assert report["whole_history_json_equal"] is True
    assert report["checkpoint_bytes_comparison_performed"] is False
    assert report["independent_external_vv"] is False
    assert report["release_eligible"] is False
    assert history == before
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    "backend",
    [
        "numpy_linalg_solve_dense",
        "scipy_sparse_spsolve_cpu",
        "scipy_sparse_splu_cpu_exact_1536",
    ],
)
def test_backend_and_hash_identity_differences_are_separate_from_physics(
    history, tolerances, backend
):
    other = deepcopy(history)
    other["configuration"]["matrix_backend"] = backend
    other["source_result_hash"] = _hash("other-source")
    descriptor = other["checkpoint_identity"]
    for key in (
        "artifact_hash",
        "chain_hash",
        "root_state_hash",
        "terminal_state_hash",
    ):
        descriptor[key] = _hash("other-" + key)
    other["root"]["state_hash"] = descriptor["root_state_hash"]
    other["steps"][0].update(
        parent_state_hash=descriptor["root_state_hash"],
        state_hash=_hash("middle-other"),
    )
    other["steps"][1].update(
        parent_state_hash=_hash("middle-other"),
        state_hash=descriptor["terminal_state_hash"],
    )
    report = _compare(history, _seal(other), tolerances)
    assert report["full_history_match"] is True
    assert report["whole_history_json_equal"] is False
    assert report["numerical_match_requires_hash_equality"] is False
    assert not report["identity_comparison"]["chain_hash_equal"]
    assert not any(
        row["state_hash_equal"] for row in report["identity_comparison"]["steps"]
    )


@pytest.mark.parametrize("group", HISTORY_GROUPS)
def test_rehashed_middle_response_change_fails_with_identical_terminal(
    history, tolerances, group
):
    other = deepcopy(history)
    first = other["steps"][0]
    if group == "material_states":
        first[group][0]["state"]["stress_mpa"] += 1.0
    else:
        first["si_rows"][group][0]["synthetic_extra_float"] = 1.0
    assert other["steps"][-1] == history["steps"][-1]
    report = _compare(history, _seal(other), tolerances)
    assert report["full_history_match"] is False
    assert report["step_comparisons"][0]["match"] is False
    assert report["step_comparisons"][1]["match"] is True
    assert report["groups"][group]["mismatch_count"] == 1
    assert report["groups"][group]["mismatch_paths"][0].startswith("/steps/0/")
    assert report["identity_comparison"]["terminal_state_hash_equal"] is True


@pytest.mark.parametrize("group", ["node_displacements", "material_states"])
def test_genesis_changes_use_their_group_tolerance(history, tolerances, group):
    other = deepcopy(history)
    if group == "node_displacements":
        other["root"]["global_displacements"][1] = 0.125
    else:
        other["root"]["material_states"][0]["state"]["strain"] = 0.125
    _seal(other)
    assert _compare(history, other, tolerances)["root_comparison"]["match"] is False
    tolerances[group]["absolute"] = 0.125
    report = _compare(history, other, tolerances)
    assert report["full_history_match"] is True
    assert report["groups"][group]["maximum_absolute_difference"] == 0.125
    tolerances[group]["absolute"] = math.nextafter(0.125, 0.0)
    assert _compare(history, other, tolerances)["full_history_match"] is False


def test_material_tolerance_does_not_change_si_tolerance(history, tolerances):
    other = deepcopy(history)
    other["steps"][0]["material_states"][0]["state"]["strain"] += 1.0
    other["steps"][0]["si_rows"]["fiber_results"][0]["strain"] += 1.0
    tolerances["material_states"]["absolute"] = 1.0
    report = _compare(history, _seal(other), tolerances)
    assert report["groups"]["material_states"]["match"] is True
    assert report["groups"]["fiber_results"]["match"] is False


def test_symmetric_relative_tolerance(history, tolerances):
    other = deepcopy(history)
    other["steps"][0]["si_rows"]["fiber_results"][0]["strain"] = 2.0
    _seal(other)
    tolerances["fiber_results"]["relative"] = 0.5
    assert _compare(history, other, tolerances)["full_history_match"] is True
    assert _compare(other, history, tolerances)["full_history_match"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("step_index", 2),
        ("step_index", 1.0),
        ("step_index", True),
        ("yielded", 0),
        ("yielded", True),
        ("optional", 0),
        ("optional", "None"),
        ("schema_version", "other"),
    ],
)
def test_material_nonfloat_fields_are_exact_even_with_large_tolerance(
    history, tolerances, field, value
):
    other = deepcopy(history)
    other["steps"][0]["material_states"][0]["state"][field] = value
    tolerances["material_states"] = {"absolute": 1e10, "relative": 1e10}
    report = _compare(history, _seal(other), tolerances)
    assert report["full_history_match"] is False
    assert report["groups"]["material_states"]["mismatch_count"] == 1


def test_state_key_membership_and_row_order_are_exact(history, tolerances):
    other = deepcopy(history)
    del other["steps"][0]["material_states"][0]["state"]["optional"]
    assert _compare(history, _seal(other), tolerances)["full_history_match"] is False
    other = deepcopy(history)
    for row in [other["root"], *other["steps"]]:
        row["material_states"].reverse()
    assert _compare(history, _seal(other), tolerances)["full_history_match"] is False


def test_config_or_model_domain_mismatch_is_unavailable(history, tolerances):
    for change in ("model", "configuration"):
        other = deepcopy(history)
        if change == "model":
            other["model_identity"]["model_ir_content_hash"] = _hash("other-model")
        else:
            other["configuration"]["residual_tolerance"] = 1e-9
        report = _compare(history, _seal(other), tolerances)
        assert report["comparison_available"] is False
        assert report["full_history_match"] is None
        assert report["full_history_float_comparison_performed"] is False
        assert report["step_counts"]["compared"] == 0
        assert all(row["match"] is None for row in report["groups"].values())


@pytest.mark.parametrize(
    "change",
    [
        lambda h: h.pop("root"),
        lambda h: h.update(extra=True),
        lambda h: h.update(schema_version="unknown"),
        lambda h: h.update(source_result_hash="bad"),
        lambda h: h["configuration"].update(control="arc_length"),
        lambda h: h["configuration"].update(load_steps=True),
        lambda h: h["configuration"].update(load_steps=1),
        lambda h: h["configuration"].update(load_steps=65),
        lambda h: h["configuration"].update(maximum_iterations=0),
        lambda h: h["configuration"].update(matrix_backend="unknown"),
        lambda h: h["configuration"].update(residual_tolerance=False),
        lambda h: h["checkpoint_identity"].update(available=1),
        lambda h: h["checkpoint_identity"].update(complete_ancestry_included=False),
        lambda h: h["checkpoint_identity"].update(prefix_replay_required=False),
        lambda h: h["checkpoint_identity"].update(artifact_byte_length=0),
        lambda h: h["checkpoint_identity"].update(terminal_epoch=1),
        lambda h: h["checkpoint_identity"].update(terminal_load_factor=1),
        lambda h: h["checkpoint_identity"].update(root_state_hash=_hash("detached")),
        lambda h: h["checkpoint_identity"].update(
            terminal_state_hash=_hash("detached")
        ),
        lambda h: h["root"].update(epoch=False),
        lambda h: h["root"].update(load_factor=0),
        lambda h: h["root"].update(global_displacements=[]),
        lambda h: h["root"]["global_displacements"].pop(),
        lambda h: h["root"]["global_displacements"].__setitem__(0, 0),
        lambda h: h.update(steps=[]),
        lambda h: h["steps"].pop(0),
        lambda h: h["steps"].reverse(),
        lambda h: h["steps"][0].update(epoch=True),
        lambda h: h["steps"][0].update(step_index=2),
        lambda h: h["steps"][0].update(load_factor=0.75),
        lambda h: h["steps"][1].update(parent_state_hash=_hash("unrelated")),
        lambda h: h["steps"][0]["si_rows"]["node_displacements"].pop(),
        lambda h: h["steps"][0]["material_states"].pop(),
        lambda h: h["steps"][0]["material_states"].reverse(),
        lambda h: h["steps"][0]["material_states"][0].update(fiber_index=False),
        lambda h: h["steps"][0]["material_states"][0]["state"].update(
            state_hash=_hash("removed-field")
        ),
        lambda h: h["claim_boundary"].update(independent_external_vv=True),
        lambda h: h["claim_boundary"].update(each_transition_reassembled=1),
    ],
)
def test_rehashed_incomplete_or_detached_history_fails_closed(
    history, tolerances, change
):
    change(history)
    with pytest.raises(ValueError):
        _compare(_seal(history), deepcopy(history), tolerances)


@pytest.mark.parametrize("group", HISTORY_GROUPS)
@pytest.mark.parametrize("bad", [[], [{}], [{"label": "only"}], None])
def test_empty_or_nonnumeric_groups_cannot_match_vacuously(
    history, tolerances, group, bad
):
    if group == "material_states":
        history["steps"][0][group] = bad
    else:
        history["steps"][0]["si_rows"][group] = bad
    with pytest.raises(ValueError):
        _compare(_seal(history), deepcopy(history), tolerances)


def test_stale_history_hash_rejects_mutation(history, tolerances):
    history["steps"][0]["si_rows"]["fiber_results"][0]["strain"] += 1.0
    with pytest.raises(ValueError, match="history hash"):
        _compare(history, history, tolerances)


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), -float("inf"), (0.0,), object()]
)
def test_nonfinite_or_nonjson_values_are_rejected(history, tolerances, bad):
    history["steps"][0]["si_rows"]["fiber_results"][0]["strain"] = bad
    with pytest.raises(ValueError):
        _compare(history, history, tolerances)


@pytest.mark.parametrize(
    "bad", [True, -1, float("nan"), float("inf"), "0", None, 10**1000]
)
def test_tolerances_are_strict_finite_nonnegative(history, tolerances, bad):
    tolerances["material_states"]["absolute"] = bad
    with pytest.raises(ValueError, match="tolerances"):
        _compare(history, history, tolerances)


def test_exact_six_tolerance_groups_and_fields_required(history, tolerances):
    for value in (
        {group: tolerances[group] for group in SI_ROWS},
        {**tolerances, "extra": {"absolute": 0, "relative": 0}},
        {**tolerances, "material_states": {"absolute": 0}},
    ):
        with pytest.raises(ValueError, match="tolerances"):
            _compare(history, history, value)


def test_mismatch_paths_are_bounded_across_all_epochs(history, tolerances):
    for row in history["steps"]:
        row["si_rows"]["fiber_results"][0]["many"] = [0.0] * 40
    _seal(history)
    other = deepcopy(history)
    for row in other["steps"]:
        row["si_rows"]["fiber_results"][0]["many"] = [1.0] * 40
    report = _compare(history, _seal(other), tolerances)
    group = report["groups"]["fiber_results"]
    assert group["mismatch_count"] == 80
    assert len(group["mismatch_paths"]) == 32
    assert group["mismatch_paths_truncated"] is True
    assert group["maximum_absolute_difference"] == 1.0
    assert len(report["step_comparisons"]) == 2


def test_float_overflow_never_passes_via_inf_comparison(history, tolerances):
    history["steps"][0]["si_rows"]["fiber_results"][0]["strain"] = -1.7e308
    _seal(history)
    other = deepcopy(history)
    other["steps"][0]["si_rows"]["fiber_results"][0]["strain"] = 1.7e308
    _seal(other)
    tolerances["fiber_results"] = {"absolute": 0.0, "relative": 1.5}
    report = _compare(history, other, tolerances)
    assert report["full_history_match"] is False
    assert report["groups"]["fiber_results"]["absolute_difference_overflow"] is True
    assert report["groups"]["fiber_results"]["maximum_absolute_difference"] is None
    json.dumps(report, allow_nan=False)
    tolerances["fiber_results"]["relative"] = 2.0
    assert _compare(history, other, tolerances)["full_history_match"] is True


def test_signed_zero_is_numerically_equal_but_keeps_history_identity(
    history, tolerances
):
    other = deepcopy(history)
    other["root"]["global_displacements"][0] = -0.0
    report = _compare(history, _seal(other), tolerances)
    assert report["full_history_match"] is True
    assert report["whole_history_json_equal"] is False
