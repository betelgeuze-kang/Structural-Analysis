"""Arithmetic/artifact comparison contracts; fixtures grant no solver authority."""

from copy import deepcopy
import hashlib
import json
import math

import pytest

from structural_analysis.benchmark.planar_frame_backend_comparison import (
    SI_ROWS,
    compare_planar_frame_results,
)


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture
def result():
    # This deliberately small source-shaped fixture exercises the comparator,
    # whose caller separately validates the full public/source/checkpoint APIs.
    identity = {
        "model_ir_content_hash": _hash(b"model-content"),
        "model_ir_semantic_hash": _hash(b"model-semantics"),
        "model_ir_provenance_hash": _hash(b"model-provenance"),
        "canonical_model_checksum": _hash(b"canonical-model"),
    }
    source = {
        "schema_version": "unified-nonlinear-frame-result.v1",
        "profile": "corotational_connected_frame2d.v1",
        "status": "ready",
        "contract_pass": True,
        "canonical_model_checksum": identity["canonical_model_checksum"],
        "input_checksum": identity["model_ir_content_hash"],
        "contract_bindings": {"source_model_ir_adapter": identity},
        "configuration": {"matrix_backend": "numpy_linalg_solve_dense"},
        "node_displacements": [{"node_id": "N1", "UX_m": 1.0}],
        "support_reactions": [
            {"node_id": "N1", "dof": "UX", "unit": "N", "value_si": 2.0}
        ],
        "member_end_forces": [
            {
                "member_id": "M1",
                "local_end_i": {"FX_N": 3.0},
                "features": {"released": False, "mass": None},
            }
        ],
        "section_results": [
            {"member_id": "M1", "integration_point_index": 0, "axial_force_N": 4.0}
        ],
        "fiber_results": [{"member_id": "M1", "fiber_index": 0, "strain": 0.005}],
        "checkpoint": {
            "available": True,
            "artifact_hash": _hash(b"checkpoint"),
            "artifact_byte_length": len(b"checkpoint"),
            "chain_hash": _hash(b"chain"),
            "root_state_hash": _hash(b"root"),
            "terminal_state_hash": _hash(b"terminal"),
            "terminal_epoch": 2,
            "terminal_load_factor": 1.0,
        },
    }
    return {
        "schema_version": "planar-frame-result.v1",
        "profile": "planar_frame_verified_alpha.v1",
        "status": "converged",
        "converged": True,
        "result_hash": _hash(b"synthetic-result"),
        "result_ir": source,
    }


@pytest.fixture
def tolerances():
    return {group: {"absolute": 0.0, "relative": 0.0} for group in SI_ROWS}


def _compare(left, right, tolerances, left_checkpoint=None, right_checkpoint=None):
    return compare_planar_frame_results(
        left,
        right,
        tolerances=tolerances,
        left_checkpoint=left_checkpoint,
        right_checkpoint=right_checkpoint,
    )


def test_complete_equal_terminal_responses_and_checkpoints(result, tolerances):
    before = deepcopy(result)
    report = _compare(
        result, deepcopy(result), tolerances, b"checkpoint", b"checkpoint"
    )
    assert report["comparison_available"]
    assert report["physical_si_match"] is True
    assert report["whole_result_json_equal"] is True
    assert report["left_result_json_sha256"] == report["right_result_json_sha256"]
    assert report["checkpoint_bytes_equal"] is True
    assert all(report["checkpoint_identity_comparison"].values())
    assert report["independent_external_vv"] is False
    assert report["full_history_float_comparison_performed"] is False
    assert all(row["float_leaf_count"] == 1 for row in report["groups"].values())
    assert all(
        row["maximum_absolute_difference"] == 0.0 for row in report["groups"].values()
    )
    assert result == before
    json.dumps(report, allow_nan=False)


def test_backend_and_result_hash_differences_do_not_fail_physical_comparison(
    result, tolerances
):
    other = deepcopy(result)
    other["result_hash"] = _hash(b"other-backend-result")
    other["result_ir"]["configuration"]["matrix_backend"] = (
        "scipy_sparse_splu_cpu_exact_1536"
    )
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is True
    assert report["whole_result_json_equal"] is False
    assert report["checkpoint_bytes_equal"] is None


def test_symmetric_relative_tolerance_and_absolute_boundary(result, tolerances):
    other = deepcopy(result)
    other["result_ir"]["node_displacements"][0]["UX_m"] = 2.0
    tolerances["node_displacements"]["relative"] = 0.5
    for left, right in ((result, other), (other, result)):
        report = _compare(left, right, tolerances)
        assert report["physical_si_match"] is True
        assert (
            report["groups"]["node_displacements"]["maximum_absolute_difference"] == 1.0
        )
    tolerances["node_displacements"] = {"absolute": 1.0, "relative": 0.0}
    assert _compare(result, other, tolerances)["physical_si_match"] is True
    tolerances["node_displacements"]["absolute"] = math.nextafter(1.0, 0.0)
    assert _compare(result, other, tolerances)["physical_si_match"] is False


@pytest.mark.parametrize(
    "group,field",
    [
        ("node_displacements", "UX_m"),
        ("support_reactions", "value_si"),
        ("section_results", "axial_force_N"),
        ("fiber_results", "strain"),
    ],
)
def test_each_group_uses_only_its_declared_tolerance(result, tolerances, group, field):
    other = deepcopy(result)
    other["result_ir"][group][0][field] += 1.0
    tolerances["member_end_forces"]["absolute"] = 1000.0
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is False
    assert report["groups"][group]["mismatch_count"] == 1
    assert report["groups"][group]["mismatch_paths"] == [
        f"/result_ir/{group}/0/{field}"
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("integration_point_index", 1),
        ("integration_point_index", 0.0),
        ("integration_point_index", False),
        ("member_id", "M2"),
    ],
)
def test_integer_identifiers_types_and_labels_remain_exact(
    result, tolerances, field, value
):
    other = deepcopy(result)
    other["result_ir"]["section_results"][0][field] = value
    tolerances["section_results"] = {"absolute": 1e6, "relative": 1e6}
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is False
    assert report["groups"]["section_results"]["mismatch_count"] == 1


@pytest.mark.parametrize(
    "field,value", [("released", 0), ("released", True), ("mass", 0), ("mass", "None")]
)
def test_nested_boolean_and_null_values_remain_exact(result, tolerances, field, value):
    other = deepcopy(result)
    other["result_ir"]["member_end_forces"][0]["features"][field] = value
    assert _compare(result, other, tolerances)["physical_si_match"] is False


def test_dictionary_key_order_is_ignored_but_row_order_and_membership_are_exact(
    result, tolerances
):
    other = json.loads(json.dumps(result, sort_keys=True))
    assert _compare(result, other, tolerances)["whole_result_json_equal"] is True
    result["result_ir"]["node_displacements"].append({"node_id": "N2", "UX_m": 2.0})
    other = deepcopy(result)
    other["result_ir"]["node_displacements"].reverse()
    report = _compare(result, other, tolerances)
    assert report["groups"]["node_displacements"]["mismatch_count"] == 4
    other = deepcopy(result)
    del other["result_ir"]["node_displacements"][0]["node_id"]
    assert _compare(result, other, tolerances)["physical_si_match"] is False
    other = deepcopy(result)
    other["result_ir"]["node_displacements"].pop()
    row = _compare(result, other, tolerances)["groups"]["node_displacements"]
    assert row["mismatch_paths"] == ["/result_ir/node_displacements/length"]


@pytest.mark.parametrize("bad", [[], [{}], [{"member_id": "M1"}], None, [1.0]])
def test_required_groups_cannot_match_vacuously(result, tolerances, bad):
    result["result_ir"]["fiber_results"] = bad
    report = _compare(result, deepcopy(result), tolerances)
    assert report["comparison_available"] is False
    assert report["physical_si_match"] is None
    assert report["whole_result_json_equal"] is True
    assert (
        "left_fiber_results_nonempty_numeric_rows_required"
        in report["unavailable_reasons"]
    )


def test_missing_group_is_unavailable(result, tolerances):
    del result["result_ir"]["support_reactions"]
    report = _compare(result, result, tolerances)
    assert not report["comparison_available"]
    assert report["groups"]["support_reactions"]["left_row_count"] is None


@pytest.mark.parametrize("status", ["not_run", "not_converged"])
def test_nonconverged_artifact_contract_cannot_grant_comparison(
    result, tolerances, status
):
    other = deepcopy(result)
    other.update(status=status, converged=None if status == "not_run" else False)
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is None
    assert not report["comparison_available"]


@pytest.mark.parametrize(
    "field",
    [
        "model_ir_content_hash",
        "model_ir_semantic_hash",
        "model_ir_provenance_hash",
        "canonical_model_checksum",
    ],
)
def test_distinct_model_identity_cannot_compare_equal_rows(result, tolerances, field):
    other = deepcopy(result)
    binding = other["result_ir"]["contract_bindings"]["source_model_ir_adapter"]
    binding[field] = _hash(b"other model")
    other["result_ir"]["input_checksum"] = binding["model_ir_content_hash"]
    other["result_ir"]["canonical_model_checksum"] = binding["canonical_model_checksum"]
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is None
    assert report["unavailable_reasons"] == ["source_model_identity_mismatch"]


@pytest.mark.parametrize("mutation", ["missing", "detached", "malformed"])
def test_missing_or_detached_source_identity_is_unavailable(
    result, tolerances, mutation
):
    if mutation == "missing":
        del result["result_ir"]["contract_bindings"]["source_model_ir_adapter"]
    elif mutation == "detached":
        result["result_ir"]["canonical_model_checksum"] = _hash(b"detached")
    else:
        result["result_ir"]["contract_bindings"]["source_model_ir_adapter"][
            "model_ir_content_hash"
        ] = "not-a-hash"
    assert _compare(result, result, tolerances)["unavailable_reasons"] == [
        "source_model_identity_unavailable"
    ]


@pytest.mark.parametrize("bad", [True, -1, math.inf, math.nan, "0", 10**1000])
@pytest.mark.parametrize("key", ["absolute", "relative"])
def test_invalid_tolerance_leaves_rejected(result, tolerances, bad, key):
    tolerances["fiber_results"][key] = bad
    with pytest.raises(ValueError, match="finite and nonnegative"):
        _compare(result, result, tolerances)


@pytest.mark.parametrize(
    "mutation",
    ["missing_group", "extra_group", "missing_key", "extra_key", "not_object"],
)
def test_exact_tolerance_field_contract(result, tolerances, mutation):
    if mutation == "missing_group":
        del tolerances["node_displacements"]
    elif mutation == "extra_group":
        tolerances["other"] = {"absolute": 0.0, "relative": 0.0}
    elif mutation == "missing_key":
        del tolerances["node_displacements"]["relative"]
    elif mutation == "extra_key":
        tolerances["node_displacements"]["epsilon"] = 1.0
    else:
        tolerances["node_displacements"] = []
    with pytest.raises(ValueError):
        _compare(result, result, tolerances)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_result_rejected_even_outside_si_groups(result, tolerances, bad):
    result["nonphysical_metadata"] = bad
    with pytest.raises(ValueError, match="finite"):
        _compare(result, result, tolerances)


def test_mismatch_paths_bounded_but_count_complete(result, tolerances):
    result["result_ir"]["node_displacements"] = [
        {"node_id": f"N{i}", "UX_m": float(i)} for i in range(100)
    ]
    other = deepcopy(result)
    for row in other["result_ir"]["node_displacements"]:
        row["UX_m"] += 0.5
    row = _compare(result, other, tolerances)["groups"]["node_displacements"]
    assert row["mismatch_count"] == row["float_leaf_count"] == 100
    assert row["maximum_absolute_difference"] == 0.5
    assert len(row["mismatch_paths"]) == 32
    assert row["mismatch_paths_truncated"] is True


def test_overflow_safe_closeness_and_serializable_maximum(result, tolerances):
    result["result_ir"]["node_displacements"][0]["UX_m"] = 1e308
    other = deepcopy(result)
    other["result_ir"]["node_displacements"][0]["UX_m"] = -1e308
    tolerances["node_displacements"]["relative"] = 1.9
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is False  # inf <= inf must not pass.
    row = report["groups"]["node_displacements"]
    assert row["absolute_difference_overflow"] is True
    assert row["maximum_absolute_difference"] is None
    json.dumps(report, allow_nan=False)
    tolerances["node_displacements"]["relative"] = 2.0
    assert _compare(result, other, tolerances)["physical_si_match"] is True


def test_signed_zero_is_physically_equal_but_distinct_json(result, tolerances):
    result["result_ir"]["node_displacements"][0]["UX_m"] = 0.0
    other = deepcopy(result)
    other["result_ir"]["node_displacements"][0]["UX_m"] = -0.0
    report = _compare(result, other, tolerances)
    assert report["physical_si_match"] is True
    assert report["whole_result_json_equal"] is False


def test_checkpoint_difference_has_no_full_history_float_claim(result, tolerances):
    other = deepcopy(result)
    data = b"different checkpoint"
    descriptor = other["result_ir"]["checkpoint"]
    descriptor.update(
        artifact_hash=_hash(data),
        artifact_byte_length=len(data),
        terminal_state_hash=_hash(b"different terminal"),
        chain_hash=_hash(b"different chain"),
    )
    report = _compare(result, other, tolerances, b"checkpoint", data)
    assert report["physical_si_match"] is True
    assert report["checkpoint_bytes_equal"] is False
    assert report["checkpoint_identity_comparison"]["terminal_epoch_equal"] is True
    assert (
        report["checkpoint_identity_comparison"]["terminal_state_hash_equal"] is False
    )
    assert report["full_history_float_comparison_performed"] is False


@pytest.mark.parametrize("data", [b"detached", b"", bytearray(b"checkpoint")])
def test_checkpoint_bytes_bound_to_own_artifact_descriptor(result, tolerances, data):
    with pytest.raises(ValueError, match="checkpoint"):
        _compare(result, result, tolerances, data, b"checkpoint")


def test_checkpoint_descriptors_without_raw_bytes_are_identity_only(result, tolerances):
    report = _compare(result, result, tolerances)
    assert report["checkpoint_identity_comparison"]["chain_hash_equal"] is True
    assert report["checkpoint_bytes_equal"] is None
    assert report["full_history_float_comparison_performed"] is False
