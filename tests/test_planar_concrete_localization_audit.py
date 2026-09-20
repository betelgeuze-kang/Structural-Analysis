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


def common_points():
    from scripts.probe_planar_common_material_points import FIELDS

    points = []
    for cell, (a, b) in enumerate(((0., 1.), (1., 0.))):
        points.append({'member': 'E1', 'gauss': 0, 'coarse_cell': cell,
                       'y_m': float(cell), 'coarse_replay_exact': True,
                       'rows': [{'target_m': 0.002,
                                 'coarse_accepted_values': dict.fromkeys((*FIELDS, 'stress_mpa'), a),
                                 'derived_fine_point_values': dict.fromkeys((*FIELDS, 'stress_mpa'), b)}]})
    return points


def test_all_common_points_keep_unsigned_error_and_maximum_location():
    from scripts.probe_planar_common_material_points import summarize_all_points

    result = summarize_all_points(common_points())
    assert result['point_count'] == result['point_target_count'] == 2
    for field in result['targets'][0]['fields'].values():
        assert field['maximum_absolute_difference'] == field['mean_absolute_difference'] == 1
        assert field['maximum_location']['coarse_cell'] == 0


@pytest.mark.parametrize('mutation', ['duplicate', 'missing_target', 'unverified', 'nan'])
def test_all_common_points_reject_incomplete_or_unknown_observations(mutation):
    from scripts.probe_planar_common_material_points import summarize_all_points

    points = common_points()
    if mutation == 'duplicate':
        points.append(points[0])
    elif mutation == 'missing_target':
        points[1]['rows'] = []
    elif mutation == 'unverified':
        points[1]['coarse_replay_exact'] = False
    else:
        points[1]['rows'][0]['derived_fine_point_values']['stress_mpa'] = float('nan')
    with pytest.raises(ValueError):
        summarize_all_points(points)


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


@pytest.mark.parametrize('limit', [True, 0, -1, 1.5, '16'])
def test_invalid_file_limit_rejected_before_open(tmp_path, limit):
    with pytest.raises(ValueError, match='positive integer'):
        read_checked(tmp_path / 'missing.json', '0' * 64, maximum_bytes=limit)


def test_oversized_file_rejected_without_reading_payload(tmp_path, monkeypatch):
    import io

    p = tmp_path / 'oversized.json'
    p.write_bytes(b'{"value":12345}')

    class UnreadablePayload(io.BufferedReader):
        def read(self, *args):
            pytest.fail('oversized payload was read')

    monkeypatch.setattr(type(p), 'open', lambda self, mode: UnreadablePayload(io.FileIO(self, mode)))
    with pytest.raises(ValueError, match='exceeds maximum_bytes'):
        read_checked(p, '0' * 64, maximum_bytes=4)


def test_exact_file_limit_and_changed_size(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    p = tmp_path / 'source.json'
    raw = b'{"value":1}'
    p.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert read_checked(p, digest, maximum_bytes=len(raw)) == {'value': 1}
    for stale_size in (len(raw) - 1, len(raw) + 1):
        monkeypatch.setattr(os, 'fstat', lambda fd: SimpleNamespace(st_size=stale_size))
        with pytest.raises(ValueError, match='source size changed'):
            read_checked(p, digest, maximum_bytes=100)


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


def test_common_point_probe_requires_original_accepted_section():
    from scripts.probe_planar_common_material_points import section_at

    step = synthetic_step()
    assert section_at(step, "E0", 0)["generalized_strain"]["axial_strain"] == 0
    step["trial_assembly"]["member_assemblies"][0]["element_response"][
        "fiber_beam_response"
    ]["section_responses"][0]["trial_state"]["fiber_states"][0]["tensile_damage"] = 0.2
    with pytest.raises(ValueError, match="section binding"):
        section_at(step, "E0", 0)


def test_common_point_probe_rejects_modified_material_before_import(
    tmp_path, monkeypatch
):
    from scripts import probe_planar_common_material_points as probe

    p = tmp_path / "source/structural_analysis/materials/concrete_damage.py"
    p.parent.mkdir(parents=True)
    p.write_text('raise RuntimeError("must not execute")')
    monkeypatch.setattr(
        probe.subprocess, "check_output", lambda *a, **kw: b"original source"
    )
    with pytest.raises(ValueError, match="frozen material source"):
        probe.material_class(tmp_path)


def test_projection_error_decomposition_preserves_signed_cancellation():
    from scripts.decompose_planar_concrete_projection import decompose, summarize

    row = decompose(0.4, 0.8, 0.4, 0.6)
    assert row['total'] == pytest.approx(-0.1)
    assert row['history'] == pytest.approx(-0.4)
    assert row['sampling'] == pytest.approx(0.3)
    assert abs(row['residual']) <= 1e-15
    summary = summarize([{'point': ['E1', 0, 0], **row}])
    assert summary['opposite_sign_component_cells'] == 1
    assert summary['sum_absolute_history'] > summary['sum_absolute_total']


def test_projection_error_decomposition_distinguishes_history_and_sampling():
    from scripts.decompose_planar_concrete_projection import decompose

    history = decompose(0.5, 0.4, 0.4, 0.4)
    assert history['sampling'] == 0
    assert history['history'] == history['total']
    sampling = decompose(0.4, 0.4, 0, 0.6)
    assert sampling['history'] == 0
    assert sampling['sampling'] == sampling['total']
    assert sampling['mixed_onset'] is True


@pytest.mark.parametrize('bad', [True, float('nan'), float('inf'), -0.1, 1.1])
def test_projection_error_decomposition_rejects_invalid_damage(bad):
    from scripts.decompose_planar_concrete_projection import decompose

    with pytest.raises(ValueError, match='finite damage'):
        decompose(0.2, bad, 0.1, 0.3)


def test_projection_error_decomposition_rejects_duplicate_points():
    from scripts.decompose_planar_concrete_projection import decompose, summarize

    row = {'point': ['E1', 0, 0], **decompose(0.4, 0.4, 0.4, 0.4)}
    with pytest.raises(ValueError, match='duplicate point'):
        summarize([row, row])


@pytest.mark.parametrize('layers,expected', [(256, (256, 128)), (512, (512, 256)),
                                           (1024, (1024, 512)), (2048, (2048, 1024))])
def test_frozen_refinement_only_declares_original_or_next_resolution(layers, expected):
    from scripts.run_planar_256_refinement import refinement_layers

    assert refinement_layers(layers) == expected


@pytest.mark.parametrize('bad', [True, 512.0, '512', 0, 128, 4096])
def test_frozen_refinement_rejects_unplanned_resolution_before_inputs(tmp_path, bad):
    from scripts.run_planar_256_refinement import run

    with pytest.raises(ValueError, match='predeclared research layer count'):
        run(tmp_path / 'missing-source', tmp_path, tmp_path, layers=bad)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('corruption', [None, 'receipt', 'features'])
def test_2048_coarse_features_require_original_bound_receipt(tmp_path, monkeypatch, corruption):
    import json

    from scripts import audit_planar_2048_refinement as audit

    def save(name, value):
        raw = json.dumps(value).encode()
        (tmp_path / name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    features = [{'target_m': i / 500} for i in range(1, 41)]
    feature_sha = save('features.json', features)
    monkeypatch.setattr(audit, 'FEATURES_SHA', feature_sha)
    receipt_sha = save('result.json', {
        'original_full_sha256': '0' * 64 if corruption == 'receipt' else audit.COARSE_SHA,
        'features_sha256': feature_sha, 'verified_steps': 40})
    inventory_sha = save('inventory.json', {'files': [{'path': 'result.json', 'sha256': receipt_sha}]})
    monkeypatch.setattr(audit, 'COARSE_INVENTORY_SHA', inventory_sha)
    if corruption == 'features':
        save('features.json', features[:-1])
    if corruption:
        with pytest.raises(ValueError, match='provenance|digest'):
            audit.coarse_features(tmp_path)
    else:
        assert audit.coarse_features(tmp_path) == features


def test_2048_protocol_change_rejected_before_loading_features(tmp_path, monkeypatch):
    from scripts import audit_planar_2048_refinement as audit

    values = iter([{'source_revision': 'original'}, {'source_revision': 'changed'}])
    monkeypatch.setattr(audit, 'read_checked', lambda *args: next(values))
    monkeypatch.setattr(audit, 'coarse_features', lambda *args: pytest.fail('must reject first'))
    with pytest.raises(ValueError, match='protocol mismatch'):
        audit.audit(tmp_path, tmp_path, tmp_path, '0' * 64, '0' * 64)


@pytest.mark.parametrize('layers', [128, 256, 512, 1024])
def test_refinement_comparison_preserves_projection_and_local_witness(monkeypatch, layers):
    import scripts.audit_planar_256_refinement as audit

    targets = [i / 500 for i in range(1, 41)]
    coarse = [{'metrics': {'target_control_displacement_m': t}, 'fine': False} for t in targets]
    fine = [{'metrics': {'target_control_displacement_m': t}, 'fine': True} for t in targets]

    def fake_sections(step, count, fields):
        assert count == layers * (2 if step['fine'] else 1)
        values = [dict.fromkeys(fields, 0.) for _ in range(count)]
        if step['fine']:
            values[-1] = dict.fromkeys(fields, 0.5)
        return {'E1:gauss-0': {'xi': 0., 'weight': 1., 'values': values}}

    monkeypatch.setattr(audit, 'sections', fake_sections)
    monkeypatch.setattr(audit, 'nodal_steel', lambda step, count: (['steel'], {'translations': [0.]}))
    rows, maxima = audit.compare_steps(coarse, fine, layers)
    assert len(rows) == 40
    for result in maxima['concrete'].values():
        assert result['absolute_difference'] == .25
        assert result['witness_cell'] == layers - 1
        assert result['cells'] == layers
        assert result['within_exploratory_one_percent'] is False
    assert maxima['nodal_steel']['translations']['within_exploratory_one_percent'] is True


@pytest.mark.parametrize('layers', [True, 256., 64, 2048])
def test_comparison_rejects_unplanned_resolution(layers):
    from scripts.audit_planar_256_refinement import compare_steps
    with pytest.raises(ValueError, match='layer count'):
        compare_steps([], [], layers)


def test_comparison_requires_complete_original_target_sequence():
    from scripts.audit_planar_256_refinement import compare_steps
    with pytest.raises(ValueError, match='forty targets'):
        compare_steps([], [], 256)


@pytest.mark.parametrize('module', ['scripts.audit_planar_512_refinement', 'scripts.audit_planar_1024_refinement'])
def test_large_refinement_audit_releases_original_before_next_read(monkeypatch, tmp_path, module):
    import weakref
    import importlib
    audit = importlib.import_module(module)

    class PathObject(dict):
        pass

    events, refs = [], []
    protocol = dict.fromkeys(('source_revision', 'source_manifest_sha256', 'input_sha256',
                             'target_displacements_m', 'control_global_dof', 'configuration',
                             'same_proportional_force_vector', 'constant_axial_load'), 'same')

    def read(path, digest, **kwargs):
        if path.name == 'protocol.json':
            return dict(protocol)
        assert all(ref() is None for ref in refs), 'previous full path still retained'
        value = PathObject(control_global_dof=15, steps=['steps'])
        refs.append(weakref.ref(value))
        events.append('read')
        return value

    monkeypatch.setattr(audit, 'read_checked', read)
    monkeypatch.setattr(audit, 'validate_path', lambda path: events.append('validate'))
    monkeypatch.setattr(audit, 'step_features', lambda steps, layers: events.append('extract') or [])
    monkeypatch.setattr(audit, 'compare_features', lambda *args: ([], {}))
    result = audit.audit(tmp_path / 'coarse', tmp_path / 'fine', 'digest')
    assert events == ['read', 'validate', 'extract'] * 2
    assert all(ref() is None for ref in refs)
    assert result['structural_solves'] == 0


@pytest.mark.parametrize('module', ['scripts.audit_planar_512_refinement', 'scripts.audit_planar_1024_refinement'])
def test_large_refinement_audit_does_not_extract_failed_path(monkeypatch, tmp_path, module):
    import importlib
    audit = importlib.import_module(module)
    protocol = dict.fromkeys(('source_revision', 'source_manifest_sha256', 'input_sha256',
                             'target_displacements_m', 'control_global_dof', 'configuration',
                             'same_proportional_force_vector', 'constant_axial_load'), 'same')
    monkeypatch.setattr(audit, 'read_checked', lambda *args, **kwargs: dict(protocol))

    def reject(path):
        raise ValueError('path failed')

    monkeypatch.setattr(audit, 'validate_path', reject)
    monkeypatch.setattr(audit, 'step_features', lambda *args: pytest.fail('failed path extracted'))
    with pytest.raises(ValueError, match='path failed'):
        audit.audit(tmp_path, tmp_path, 'digest')
