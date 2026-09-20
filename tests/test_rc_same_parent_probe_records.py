"""Training and probe records must preserve source bindings and prior evidence."""
import importlib
import json
from pathlib import Path

import pytest


def test_repeated_comparisons_keep_distinct_immutable_receipts(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    save_record = importlib.import_module('run_rc_same_parent_seed_probe').save_record
    first = {'pair_index': 0, 'repetition': 0, 'report_hash': 'first'}
    second = {'pair_index': 0, 'repetition': 1, 'report_hash': 'second'}
    save_record(tmp_path, first)
    save_record(tmp_path, second)
    assert json.loads((tmp_path / 'record-000-0.json').read_text()) == first
    assert json.loads((tmp_path / 'record-000-1.json').read_text()) == second
    with pytest.raises(FileExistsError):
        save_record(tmp_path, {**first, 'report_hash': 'replacement'})
    assert json.loads((tmp_path / 'record-000-0.json').read_text()) == first


def test_interior_label_reader_rejects_ambiguous_json(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    read = importlib.import_module('audit_rc_interior_training_coverage').read
    path = tmp_path / 'samples.json'
    path.write_text('[{"sample_hash":"first","sample_hash":"second"}]')
    with pytest.raises(ValueError):
        read(path)


def test_interior_audit_rejects_changed_declared_request_before_reading_labels(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    audit = importlib.import_module('audit_rc_interior_training_coverage')
    _, new, combined, groups = audit.expanded_cases()
    plan = {'groups': groups, 'generation_case_ids': [c.case_id for c in new],
            'combined_cases': [{'case_id': c.case_id, 'split': c.split,
                                'model': c.model.canonical_payload(),
                                'request': c.request.to_dict()} for c in combined]}
    plan['combined_cases'][-1]['request']['targets_m'][0] *= 2
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    monkeypatch.setattr(audit, 'reader', lambda *args: None)
    with pytest.raises(ValueError, match='declared model or request changed'):
        audit.audit(tmp_path, tmp_path)
