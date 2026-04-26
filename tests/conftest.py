"""Shared fixtures for Phase 1 unit tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add phase1 implementation directory to sys.path so modules can be imported.
PHASE1_DIR = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))


# ── JSON schema fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def vehicle_schema() -> dict:
    import json
    return json.loads((PHASE1_DIR / "vehicle_model_schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def tunnel_schema() -> dict:
    import json
    return json.loads((PHASE1_DIR / "tunnel_lining_schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def soil_impedance_schema() -> dict:
    import json
    return json.loads((PHASE1_DIR / "soil_impedance_table.json").read_text(encoding="utf-8"))


@pytest.fixture
def material_rule_table() -> dict:
    import json
    return json.loads((PHASE1_DIR / "material_rule_table.json").read_text(encoding="utf-8"))


@pytest.fixture
def dynamics_boundary_schema() -> dict:
    import json
    return json.loads((PHASE1_DIR / "dynamics_boundary_contract.schema.json").read_text(encoding="utf-8"))
