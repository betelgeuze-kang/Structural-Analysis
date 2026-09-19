"""Synthetic diagnostic-contract tests, not physical validation."""

from copy import deepcopy
import hashlib

import pytest

from scripts.audit_planar_concrete_localization import (
    cell_metrics,
    read_checked,
    sections,
    validate_path,
)


def test_mixed_onset_cell_retains_large_error_despite_small_section_mean():
    result = cell_metrics([0.0] * 64, [0.0] * 100 + [0.25, 0.0] + [0.0] * 26)
    assert result["section_relative_infinity_difference"] == 1
    assert result["section_mean_absolute_damage_difference"] == 0.125 / 64
    assert result["mixed_onset_child_cells"] == 1
    assert result["mixed_onset_absolute_difference_share"] == 1
    assert result["cells_above_one_percent_section_norm"] == 1


def test_signed_cancellation_does_not_hide_absolute_difference():
    result = cell_metrics([0.0, 1.0], [1.0, 1.0, 0.0, 0.0])
    assert (
        result["coarse_section_mean_damage"]
        == result["fine_section_mean_damage"]
        == 0.5
    )
    assert result["section_mean_absolute_damage_difference"] == 1
    assert result["mixed_onset_absolute_difference_share"] == 0


def test_exact_match_has_no_mixed_error_share():
    result = cell_metrics([0.25], [0.5, 0])
    assert result["section_relative_infinity_difference"] == 0
    assert result["mixed_onset_child_cells"] == 1
    assert result["mixed_onset_absolute_difference_share"] is None


@pytest.mark.parametrize(
    "coarse,fine",
    [
        ([], []),
        ([0], [0]),
        ([True], [0, 0]),
        ([0], [float("nan"), 0]),
        ([0], [1.01, 0]),
        ([-0.1], [0, 0]),
    ],
)
def test_invalid_damage_or_correspondence_rejected(coarse, fine):
    with pytest.raises(ValueError):
        cell_metrics(coarse, fine)


def test_pinned_bytes_and_strict_duplicate_keys(tmp_path):
    p = tmp_path / "source.json"
    p.write_bytes(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match="SHA-256"):
        read_checked(p, "0" * 64)
    with pytest.raises(ValueError):
        read_checked(p, hashlib.sha256(p.read_bytes()).hexdigest())


def test_path_requires_full_accepted_parent_chain():
    step = {
        "committed": True,
        "metrics": {
            "solver_contract_pass": True,
            "target_control_displacement_m": 0.002,
        },
        "parent_checkpoint": {"x": 0},
        "accepted_checkpoint": {"x": 1},
    }
    path = {
        "status": "ready",
        "contract_pass": True,
        "initial_checkpoint": {"x": 0},
        "final_checkpoint": {"x": 1},
        "target_control_displacements_m": [0.002],
        "steps": [step],
    }
    validate_path(path)
    step["parent_checkpoint"]["x"] = 2
    with pytest.raises(ValueError, match="checkpoint chain"):
        validate_path(path)


def synthetic_step():
    elements, members = [], []
    for i in range(6):
        fibers = [
            {
                "schema_version": "uniaxial-asymmetric-concrete-damage-state.v1",
                "tensile_damage": 0.0,
                "compressive_damage": 0.0,
            }
            for _ in range(2)
        ] + [{}, {}]
        state = {"fiber_states": fibers}
        element = {
            "element_id": f"E{i}",
            "basic_beam_state": {
                "integration_point_states": [deepcopy(state) for _ in range(3)]
            },
        }
        section = {
            "trial_state": deepcopy(state),
            "generalized_strain": {"axial_strain": 0.0, "curvature_z_per_m": 0.0},
            "fiber_responses": [
                {"trial_state": deepcopy(f), "total_strain": 0.0} for f in fibers
            ],
        }
        elements.append(element)
        members.append(
            {
                "member_id": f"E{i}",
                "element_response": {
                    "trial_state": deepcopy(element),
                    "fiber_beam_response": {
                        "section_responses": [deepcopy(section) for _ in range(3)],
                        "integration_point_xi": [-0.7, 0, 0.7],
                        "integration_point_weights": [0.5, 1.0, 0.5],
                    },
                },
            }
        )
    return {
        "accepted_checkpoint": {"element_states": elements},
        "trial_assembly": {"member_assemblies": members},
    }


def test_accepted_section_binding_and_strain_location():
    step = synthetic_step()
    assert len(sections(step, 2)) == 18
    response = step["trial_assembly"]["member_assemblies"][0]["element_response"][
        "fiber_beam_response"
    ]["section_responses"][0]["fiber_responses"][0]
    response["total_strain"] = 0.1
    with pytest.raises(ValueError, match="strain location"):
        sections(step, 2)
    response["total_strain"] = 0
    response["trial_state"]["tensile_damage"] = 0.1
    with pytest.raises(ValueError, match="fiber binding"):
        sections(step, 2)


def test_duplicate_member_not_silently_overwritten():
    step = synthetic_step()
    step["trial_assembly"]["member_assemblies"].append(
        deepcopy(step["trial_assembly"]["member_assemblies"][0])
    )
    with pytest.raises(ValueError, match="duplicate section"):
        sections(step, 2)


def test_refinement_runner_rejects_manifest_before_git_or_import(tmp_path, monkeypatch):
    from scripts import run_planar_256_refinement as runner

    (tmp_path / "inputs-manifest.json").write_bytes(b"{}")

    def forbidden(*args, **kwargs):
        pytest.fail("Git should not be queried for a changed manifest")

    monkeypatch.setattr(runner.subprocess, "check_output", forbidden)
    with pytest.raises(ValueError, match="manifest changed"):
        runner.checked_sources(tmp_path, tmp_path)


@pytest.mark.parametrize("matching_identity", [False, True])
def test_refinement_runner_rejects_source_not_matching_identity_or_git(
    tmp_path, monkeypatch, matching_identity
):
    import json
    from scripts import run_planar_256_refinement as runner

    content = b"print('changed source must never execute')\n"
    path = tmp_path / "source/structural_analysis/example.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    identity = {
        "sha256": "sha256:"
        + (hashlib.sha256(content).hexdigest() if matching_identity else "0" * 64),
        "byte_length": len(content),
    }
    manifest = json.dumps({"source_files": {"example.py": identity}}).encode()
    (tmp_path / "inputs-manifest.json").write_bytes(manifest)
    monkeypatch.setattr(runner, "MANIFEST_SHA256", hashlib.sha256(manifest).hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda *a, **kw: "100644 blob "
        + "0" * 40
        + "\tsrc/structural_analysis/example.py\n",
    )
    with pytest.raises(
        ValueError,
        match="source differs from frozen Git tree"
        if matching_identity
        else "source identity mismatch",
    ):
        runner.checked_sources(tmp_path, tmp_path)


def test_projection_can_observe_response_stress_and_state_history_separately():
    step = synthetic_step()
    for member in step["trial_assembly"]["member_assemblies"]:
        for section in member["element_response"]["fiber_beam_response"][
            "section_responses"
        ]:
            for response in section["fiber_responses"]:
                response["stress_mpa"] = 2.5
    observed = sections(step, 2, ("tensile_damage", "stress_mpa"))
    assert observed["E0:gauss-0"]["values"][0] == {
        "tensile_damage": 0.0,
        "stress_mpa": 2.5,
    }


def test_refinement_group_floor_and_local_maximum_are_preserved():
    from scripts.audit_planar_256_refinement import metric

    result = metric([0.0, 1.0], [1.0, 0.0], 1e-12)
    assert result["relative_group_difference"] == 1
    assert result["within_exploratory_one_percent"] is False
    result = metric([1e-13], [0.0], 1e-12)
    assert result["relative_group_difference"] == 0.1
    assert result["denominator_floor"] == 1e-12


@pytest.mark.parametrize(
    "a,b", [([], []), ([0.0], [0.0, 0.0]), ([True], [0.0]), ([float("inf")], [1.0])]
)
def test_refinement_group_rejects_incomplete_or_nonfinite_observations(a, b):
    from scripts.audit_planar_256_refinement import metric

    with pytest.raises(ValueError):
        metric(a, b, 1e-12)
