#!/usr/bin/env python3
"""Materialize workspace and solver artifacts from a native authoring draft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.generate_native_authoring_solver_session import (
        DEFAULT_LOADCOMB_OUT,
        DEFAULT_OUT as DEFAULT_SOLVER_OUT,
        KDS_CONCRETE_FAMILY,
        materialize_native_authoring_solver_session,
    )
    from implementation.phase1.generate_native_authoring_workspace_summary import (
        DEFAULT_OUT as DEFAULT_WORKSPACE_OUT,
        resolve_authoring_controls,
        materialize_native_authoring_workspace_summary,
    )
except ImportError:  # pragma: no cover
    from generate_native_authoring_solver_session import (  # type: ignore
        DEFAULT_LOADCOMB_OUT,
        DEFAULT_OUT as DEFAULT_SOLVER_OUT,
        KDS_CONCRETE_FAMILY,
        materialize_native_authoring_solver_session,
    )
    from generate_native_authoring_workspace_summary import (  # type: ignore
        DEFAULT_OUT as DEFAULT_WORKSPACE_OUT,
        resolve_authoring_controls,
        materialize_native_authoring_workspace_summary,
    )


DEFAULT_OUT = Path("implementation/phase1/release/authoring/native_authoring_draft_pipeline.json")


def build_native_authoring_draft_pipeline(
    *,
    out_path: Path = DEFAULT_OUT,
    workspace_out_path: Path = DEFAULT_WORKSPACE_OUT,
    solver_out_path: Path = DEFAULT_SOLVER_OUT,
    loadcomb_out_path: Path = DEFAULT_LOADCOMB_OUT,
    generated_at: str | None = None,
    family: str = KDS_CONCRETE_FAMILY,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    controls = resolve_authoring_controls(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    workspace_payload = materialize_native_authoring_workspace_summary(
        out_path=workspace_out_path,
        generated_at=generated_at,
        authoring_controls=controls,
    )
    solver_payload = materialize_native_authoring_solver_session(
        out_path=solver_out_path,
        loadcomb_out_path=loadcomb_out_path,
        generated_at=generated_at,
        family=family,
        authoring_controls=controls,
    )
    payload = {
        "schema_version": "1.0",
        "report_family": "native_authoring_draft_pipeline",
        "generated_at": str(workspace_payload.get("generated_at", "") or solver_payload.get("generated_at", "") or ""),
        "authoring_controls": controls.to_draft_payload(),
        "contract_pass": bool(workspace_payload.get("contract_pass", False) and solver_payload.get("contract_pass", False)),
        "summary_line": (
            f"Native authoring draft pipeline: "
            f"{'PASS' if workspace_payload.get('contract_pass', False) and solver_payload.get('contract_pass', False) else 'CHECK'} | "
            f"workspace={Path(workspace_out_path).name} | solver={Path(solver_out_path).name} | loadcomb={Path(loadcomb_out_path).name}"
        ),
        "artifacts": {
            "workspace_summary_json": str(workspace_out_path),
            "solver_session_json": str(solver_out_path),
            "loadcomb_preview_mgt": str(loadcomb_out_path),
        },
        "workspace_summary": {
            "summary_line": str(workspace_payload.get("summary_line", "") or ""),
            "story_count": int((workspace_payload.get("summary") or {}).get("story_count", 0) or 0),
            "member_count": int((workspace_payload.get("summary") or {}).get("member_count", 0) or 0),
            "load_pattern_count": int((workspace_payload.get("summary") or {}).get("load_pattern_count", 0) or 0),
        },
        "solver_session": {
            "summary_line": str(solver_payload.get("summary_line", "") or ""),
            "mesh_request_count": int((solver_payload.get("summary") or {}).get("mesh_request_count", 0) or 0),
            "combo_count": int((solver_payload.get("summary") or {}).get("combo_count", 0) or 0),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--workspace-out", default=str(DEFAULT_WORKSPACE_OUT))
    parser.add_argument("--solver-out", default=str(DEFAULT_SOLVER_OUT))
    parser.add_argument("--loadcomb-out", default=str(DEFAULT_LOADCOMB_OUT))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--family", default=KDS_CONCRETE_FAMILY)
    parser.add_argument("--draft-json", default="")
    parser.add_argument("--family-id", default=None)
    parser.add_argument("--story-count", type=float, default=None)
    parser.add_argument("--bay-count", type=float, default=None)
    parser.add_argument("--floor-height-m", type=float, default=None)
    parser.add_argument("--load-pattern-count", type=float, default=None)
    parser.add_argument("--section-id", default=None)
    args = parser.parse_args()

    payload = build_native_authoring_draft_pipeline(
        out_path=Path(args.out),
        workspace_out_path=Path(args.workspace_out),
        solver_out_path=Path(args.solver_out),
        loadcomb_out_path=Path(args.loadcomb_out),
        generated_at=str(args.generated_at).strip() or None,
        family=str(args.family).strip() or KDS_CONCRETE_FAMILY,
        draft_json_path=str(args.draft_json).strip() or None,
        family_id=str(args.family_id).strip() if isinstance(args.family_id, str) and args.family_id.strip() else None,
        story_count=args.story_count,
        bay_count=args.bay_count,
        floor_height_m=args.floor_height_m,
        load_pattern_count=args.load_pattern_count,
        section_id=str(args.section_id).strip() if isinstance(args.section_id, str) and args.section_id.strip() else None,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
