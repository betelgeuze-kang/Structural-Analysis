from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_imported_compatibility_module_is_the_original_core_module() -> None:
    compatibility = importlib.import_module("scripts.check_generated_artifact_dag")
    core = importlib.import_module("scripts.check_generated_artifact_dag_core")
    assert compatibility is core


def test_cli_entrypoint_scopes_source_override_to_direct_execution() -> None:
    entrypoint = (ROOT / "scripts/check_generated_artifact_dag.py").read_text(
        encoding="utf-8"
    )
    assert "def _persisted_observation_source" in entrypoint
    assert "def _run_cli" in entrypoint
    assert "_core.PRODUCT_STATE_NIGHTLY_SOURCE = observed_source" in entrypoint
    assert "sys.modules[__name__] = _core" in entrypoint
    assert "_core._validate_product_state_binding =" not in entrypoint
