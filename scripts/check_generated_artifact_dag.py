#!/usr/bin/env python3
"""Validate the artifact DAG while preserving CLI product-state identity.

The unchanged implementation remains in ``check_generated_artifact_dag_core``.
Only the real CLI entry point temporarily adopts the observation-source value
persisted in the product-state artifact. Imported producer validators retain
their original semantics for candidate scopes and focused test fixtures.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_generated_artifact_dag_core as _core


for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))


def _repo_root_from_argv(argv: Sequence[str] | None) -> Path:
    arguments = list(sys.argv[1:] if argv is None else argv)
    for index, argument in enumerate(arguments):
        if argument == "--repo-root":
            if index + 1 >= len(arguments):
                return ROOT
            return Path(arguments[index + 1]).resolve()
        if argument.startswith("--repo-root="):
            return Path(argument.split("=", 1)[1]).resolve()
    return ROOT


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


def main(argv: list[str] | None = None) -> int:
    repo_root = _repo_root_from_argv(argv)
    observed_source = _observed_product_state_source(repo_root)
    previous_source = _core.PRODUCT_STATE_NIGHTLY_SOURCE
    try:
        if observed_source is not None:
            _core.PRODUCT_STATE_NIGHTLY_SOURCE = observed_source
        return _core.main(argv)
    finally:
        _core.PRODUCT_STATE_NIGHTLY_SOURCE = previous_source


if __name__ == "__main__":
    raise SystemExit(main())
