#!/usr/bin/env python3
"""Generate a deterministic multi-project registry index artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from implementation.phase1.project_registry_service import build_project_registry_index
except ImportError:  # pragma: no cover
    from project_registry_service import build_project_registry_index  # type: ignore


DEFAULT_OUT = Path("implementation/phase1/release/project_registry_index.json")
DEFAULT_WORKSPACE_OUT = Path("implementation/phase1/release/project_registry_portfolio_workspace.json")
DEFAULT_REGISTRIES = (
    Path("implementation/phase1/release/project_registry.json"),
    Path("implementation/phase1/release/release_registry.json"),
)


def _parse_path_csv(raw: str) -> list[Path]:
    return [Path(item.strip()) for item in str(raw or "").split(",") if item.strip()]


def _parse_string_csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry-paths",
        default=",".join(str(path) for path in DEFAULT_REGISTRIES),
        help="Comma-separated files, directories, or glob patterns for registry discovery.",
    )
    parser.add_argument("--registry-dirs", default="", help="Comma-separated directories to scan recursively.")
    parser.add_argument("--registry-globs", default="", help="Comma-separated glob patterns to expand recursively.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--workspace-out",
        default="",
        help="Optional companion workspace artifact. Defaults under the release root when --out uses the default path.",
    )
    args = parser.parse_args()

    registry_paths = _parse_path_csv(args.registry_paths)
    registry_dirs = _parse_path_csv(args.registry_dirs)
    registry_globs = _parse_string_csv(args.registry_globs)
    workspace_out = Path(args.workspace_out) if str(args.workspace_out).strip() else None
    if workspace_out is None and Path(args.out) == DEFAULT_OUT:
        workspace_out = DEFAULT_WORKSPACE_OUT
    payload = build_project_registry_index(
        registry_paths=registry_paths,
        registry_dirs=registry_dirs,
        registry_globs=registry_globs,
        workspace_out=workspace_out,
        out=Path(args.out),
    )
    print(payload["summary_line"])
    if str(payload.get("reason_code")) == "ERR_INPUT":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
