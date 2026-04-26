#!/usr/bin/env python3
"""Runtime input-contract validation and structured logging helpers."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from jsonschema import Draft202012Validator


class InputContractError(ValueError):
    """Raised when runtime input payload violates JSON schema contract."""


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for compact JSON-line events."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a structured log line as a single JSON object."""
    payload: dict[str, Any] = {"event": str(event)}
    payload.update(fields)
    logger.log(level, json.dumps(payload, ensure_ascii=True, sort_keys=True))


def validate_input_contract(instance: dict[str, Any], schema: dict[str, Any], *, label: str) -> None:
    """Validate input payload against JSON schema and raise readable error."""
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return

    parts: list[str] = []
    for err in errors[:6]:
        path = ".".join(str(x) for x in err.path) or "<root>"
        parts.append(f"{path}: {err.message}")
    msg = "; ".join(parts)
    raise InputContractError(f"{label} contract violation: {msg}")

