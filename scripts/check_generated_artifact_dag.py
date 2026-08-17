#!/usr/bin/env python3
"""Validate the artifact DAG while preserving product-state source identity.

The implementation remains in ``check_generated_artifact_dag_core``. This
entry point keeps the historical import/CLI surface and makes exact producer
rebuilds use the observation-source identifier already recorded in the
persisted product-state artifact.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_generated_artifact_dag_core as _core


for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))

_ORIGINAL_PRODUCT_STATE_VALIDATOR = _core._validate_product_state_binding


def _observed_product_state_source(repo_root: Path) -> str | None:
    output_path = repo_root / _core.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    if not output_path.is_file():
        return None
    try:
        payload: dict[str, Any] = _core._load_json_object(output_path)
    except (OSError, ValueError):
        return None
    source = payload.get("observed_github_main_source")
    if not isinstance(source, str) or not source.strip():
        return None
    return source.strip()


def _validate_product_state_binding(
    repo_root: Path,
    *,
    nightly_workflow_run_event: Path | None,
) -> list[str]:
    observed_source = _observed_product_state_source(repo_root)
    if observed_source is None:
        return ["product_state_observed_main_source_missing"]

    previous_source = _core.PRODUCT_STATE_NIGHTLY_SOURCE
    try:
        _core.PRODUCT_STATE_NIGHTLY_SOURCE = observed_source
        return _ORIGINAL_PRODUCT_STATE_VALIDATOR(
            repo_root,
            nightly_workflow_run_event=nightly_workflow_run_event,
        )
    finally:
        _core.PRODUCT_STATE_NIGHTLY_SOURCE = previous_source


_core._validate_product_state_binding = _validate_product_state_binding


def main(argv: list[str] | None = None) -> int:
    return _core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
