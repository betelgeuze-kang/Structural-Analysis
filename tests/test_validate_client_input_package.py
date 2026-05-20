from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "validate_client_input_package.py"
SPEC = importlib.util.spec_from_file_location("validate_client_input_package", SCRIPT_PATH)
assert SPEC is not None
validate_client_input_package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_client_input_package)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_client_input_validator_ready_case(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "model.json",
        {
            "model": {
                "nodes": [{"id": "N1", "x": 0, "y": 0, "z": 0}],
                "elements": [{"id": "E1", "i": "N1", "j": "N1"}],
                "metadata": {"units": {"length": "m", "force": "kN"}, "revision": "A"},
                "loads": {"DL": []},
            }
        },
    )

    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path)

    assert payload["schema_version"] == "client-input-validation-report.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["checks"]["coordinates_valid"] is True


def test_client_input_validator_needs_review_for_missing_units(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "model.json",
        {
            "nodes": [{"id": "N1", "x": 0, "y": 0, "z": 0}],
            "elements": [{"id": "E1"}],
        },
    )

    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path)

    assert payload["status"] == "needs_review"
    assert payload["contract_pass"] is False
    assert "unit_information_missing" in payload["needs_review"]


def test_client_input_validator_blocks_missing_package(tmp_path: Path) -> None:
    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path / "missing")

    assert payload["status"] == "blocked"
    assert "input_package_missing_or_empty" in payload["blockers"]
