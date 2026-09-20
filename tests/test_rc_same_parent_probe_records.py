"""Repeated probe results must append without overwriting completed evidence."""
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
