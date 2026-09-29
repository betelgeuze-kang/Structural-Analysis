"""Protect exact numerical comparison, including incomplete and extra receipts."""
import hashlib
import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize('change', ['none', 'changed', 'missing', 'extra', 'old_changed', 'both_missing'])
def test_fold_equivalence_rejects_receipt_mutation_or_roster_change(tmp_path, monkeypatch, change):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_scalar_runtime_equivalence')
    old = tmp_path / 'old/study/selection/fold-0000'
    new = tmp_path / 'new/study/selection/fold-0000'
    for folder in (old, new):
        (folder / 'proposal').mkdir(parents=True)
        (folder / 'proposal/000-1-step.json').write_bytes(b'{"state":"original"}')
    key = 'study/selection/fold-0000/proposal/000-1-step.json'
    raw = (old / 'proposal/000-1-step.json').read_bytes()
    index = {key: {'byte_length': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    if change == 'changed':
        (new / 'proposal/000-1-step.json').write_bytes(b'{"state":"changed"}')
    elif change == 'missing':
        (new / 'proposal/000-1-step.json').unlink()
    elif change == 'extra':
        (new / 'proposal/000-2-step.json').write_bytes(raw)
    elif change == 'both_missing':
        for folder in (old, new):
            (folder / 'proposal/000-1-step.json').unlink()
    elif change == 'old_changed':
        for folder in (old, new):
            (folder / 'proposal/000-1-step.json').write_bytes(b'{"state":"changed"}')
    if change == 'none':
        assert module.compare_fold(old, new, index)['-step.json'] == 1
    else:
        with pytest.raises(ValueError, match='changed'):
            module.compare_fold(old, new, index)


@pytest.mark.parametrize('field', [
    'model_checksum', 'compiled_problem_contract_hash', 'request',
    'absolute_tolerance', 'relative_tolerance', 'coordinate_precision',
    'fiber_strain_evaluation', 'force_accumulation', 'material_arithmetic',
    'native_checkpoint_coordinate_representation', 'strain_evaluation',
    'terminal_coordinate_precision', 'terminal_refinement_limit',
])
def test_equivalence_rejects_changed_physics_or_acceptance(tmp_path, monkeypatch, field):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('audit_rc_scalar_runtime_equivalence')
    fields = (
        'model_checksum', 'compiled_problem_contract_hash', 'request',
        'absolute_tolerance', 'relative_tolerance', 'coordinate_precision',
        'fiber_strain_evaluation', 'force_accumulation', 'material_arithmetic',
        'native_checkpoint_coordinate_representation', 'strain_evaluation',
        'terminal_coordinate_precision', 'terminal_refinement_limit',
    )
    original = dict.fromkeys(fields, 'original')
    changed = dict(original, source_revision='new', whole_study_wall_ns=99)
    module.require_same_problem_and_numerics(original, changed)
    changed[field] = 'different'
    with pytest.raises(ValueError, match='problem or numerical contract changed'):
        module.require_same_problem_and_numerics(original, changed)
    del changed[field]
    with pytest.raises(ValueError, match='problem or numerical contract changed'):
        module.require_same_problem_and_numerics(original, changed)
