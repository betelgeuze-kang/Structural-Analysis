#!/usr/bin/env python3
"""Resolve canonical MIDAS Gen same-mesh result JSON (live > env override > proxy)."""

from __future__ import annotations

import os
from pathlib import Path

from design_optimization.io import load_json


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROXY = (
    REPO_ROOT
    / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json"
)
DEFAULT_LIVE_EXAMPLE = (
    REPO_ROOT
    / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.live.example.json"
)


def resolve_midas_same_mesh_result_path(
    *,
    roundtrip_json: Path | None = None,
    prefer_live: bool | None = None,
) -> tuple[Path, str]:
    """Return (path, resolution_kind)."""
    env_path = str(os.environ.get("PHASE1_MIDAS_SAME_MESH_RESULT_JSON") or "").strip()
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path, "env_override"

    use_live = prefer_live
    if use_live is None:
        use_live = str(os.environ.get("PHASE1_USE_MIDAS_LIVE_RESULT") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    if use_live and DEFAULT_LIVE_EXAMPLE.is_file():
        return DEFAULT_LIVE_EXAMPLE, "live_example_fixture"

    if roundtrip_json and roundtrip_json.is_file():
        sibling = roundtrip_json.parent / "midas_generator_33.optimized.midas_gen_same_mesh_result.json"
        if sibling.is_file():
            payload = load_json(sibling)
            kind = str((payload.get("source") or {}).get("kind") or "")
            if kind == "midas_gen_live_export":
                return sibling, "live_sibling"
            if not use_live:
                return sibling, "proxy_sibling"

    if DEFAULT_PROXY.is_file():
        return DEFAULT_PROXY, "default_proxy"

    return DEFAULT_PROXY, "missing"
