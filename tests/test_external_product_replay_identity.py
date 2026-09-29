"""Pure replay identity contracts, independent of external receipt materialization."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "replay_identity_contract", ROOT / "scripts/run_external_code_to_code_technical_receipt.py",
)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


@pytest.mark.parametrize('reference,stored_product,current_product', [
    (0.0, 4.440892098500626e-13, -1.3322676295501878e-12),
    (4.96422719988357e-7, 4.964233584953451e-7, 4.964244685421869e-7),
])
def test_replay_near_zero_derived_error_does_not_amplify_allowed_response_drift(
    reference, stored_product, current_product,
):
    stored = module._comparison('witness', stored_product, reference)
    current = module._comparison('witness', current_product, reference)
    assert stored['contract_pass'] and current['contract_pass']
    assert module._product_replay_values_match(stored, current)


@pytest.mark.parametrize('field,value', [
    ('relative_error', 0.0), ('relative_error', float('nan')),
    ('absolute_error', 0.0), ('contract_pass', False),
    ('product_value', 1.0), ('reference_value', 1.0),
    ('quantity', 'different'), ('absolute_tolerance', 1.0),
])
def test_replay_near_zero_cannot_hide_tampered_metric(field, value):
    stored = module._comparison('witness', 4e-13, 0.0)
    current = module._comparison('witness', -1e-12, 0.0)
    current[field] = value
    assert not module._product_replay_values_match(stored, current)


def test_replay_small_drift_cannot_flip_comparison_pass():
    stored = module._comparison('witness', 1.9e-10, 0.0)
    current = module._comparison('witness', 2.1e-10, 0.0)
    assert stored['contract_pass'] and not current['contract_pass']
    assert not module._product_replay_values_match(stored, current)


def test_replay_rejects_inconsistent_stored_relative_diagnostic():
    stored = module._comparison('witness', 4e-13, 0.0)
    current = module._comparison('witness', -1e-12, 0.0)
    stored['relative_error'] = 0.0
    assert not module._product_replay_values_match(stored, current)


def test_replay_mismatch_path_uses_same_metric_acceptance_rule():
    left = module._comparison('witness', 4e-13, 0.0)
    right = module._comparison('witness', -1e-12, 0.0)
    assert module._product_replay_mismatch_path([{'metrics': [left]}], [{'metrics': [right]}]) is None
    right['contract_pass'] = False
    assert module._product_replay_mismatch_path([{'metrics': [left]}], [{'metrics': [right]}]) == (0, 'metrics', 0, 'contract_pass')


@pytest.mark.parametrize('left,right,expected', [
    ({'a': 1}, {}, ('a',)), ([1], [1, 2], (1,)),
    ([{'value': 1.0}], [{'value': 2.0}], (0, 'value')),
    (1, True, ()),
])
def test_replay_mismatch_path_retains_structural_and_scalar_failures(left, right, expected):
    assert module._product_replay_mismatch_path(left, right) == expected
