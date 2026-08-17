#!/usr/bin/env python3
"""Artifact-DAG compatibility entry point with CLI-only source identity replay."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Direct clean-checkout execution needs the repository root on sys.path before
# importing the shared implementation module.
from scripts import check_generated_artifact_dag_core as _core  # noqa: E402


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


def _persisted_observation_source(repo_root: Path) -> str | None:
    output = repo_root / _core.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    if not output.is_file():
        return None
    try:
        payload: Any = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    source = payload.get("observed_github_main_source")
    if not isinstance(source, str) or not source.strip():
        return None
    return source.strip()


def _run_cli(argv: list[str] | None = None) -> int:
    observed_source = _persisted_observation_source(_repo_root_from_argv(argv))
    previous_source = _core.PRODUCT_STATE_NIGHTLY_SOURCE
    try:
        if observed_source is not None:
            _core.PRODUCT_STATE_NIGHTLY_SOURCE = observed_source
        return _core.main(argv)
    finally:
        _core.PRODUCT_STATE_NIGHTLY_SOURCE = previous_source


if __name__ == "__main__":
    raise SystemExit(_run_cli())

# Imported callers and tests must receive the original module object so
# monkeypatches continue to affect the globals used by producer validators.
sys.modules[__name__] = _core
