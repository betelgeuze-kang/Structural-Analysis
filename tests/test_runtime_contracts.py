"""Unit tests for runtime input-contract helpers."""
from __future__ import annotations

import logging

import pytest

from runtime_contracts import InputContractError, get_logger, validate_input_contract


def test_validate_input_contract_passes_on_valid_payload() -> None:
    schema = {
        "type": "object",
        "required": ["value"],
        "additionalProperties": False,
        "properties": {"value": {"type": "number", "exclusiveMinimum": 0.0}},
    }
    payload = {"value": 1.5}
    validate_input_contract(payload, schema, label="unit.test")


def test_validate_input_contract_raises_on_invalid_payload() -> None:
    schema = {
        "type": "object",
        "required": ["count"],
        "additionalProperties": False,
        "properties": {"count": {"type": "integer", "minimum": 2}},
    }
    with pytest.raises(InputContractError, match="count"):
        validate_input_contract({"count": 1}, schema, label="unit.test")


def test_get_logger_reuses_handler_once() -> None:
    logger_name = "phase1.test.runtime_contracts"
    logger_a = get_logger(logger_name)
    before = len(logger_a.handlers)
    logger_b = get_logger(logger_name)
    after = len(logger_b.handlers)
    assert logger_a is logger_b
    assert before == after
    assert logger_a.level == logging.INFO
