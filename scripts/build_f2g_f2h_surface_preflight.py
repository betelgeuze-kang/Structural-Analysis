#!/usr/bin/env python3
"""Build the F2g/F2h authoritative surface preflight packet.

This is a non-promoting readiness check. It verifies that the current checkout
has the real MGT model, real per-element tangent evidence, near-null packet, and
support/elastic-link context required before running the F2g reconciliation audit.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUTPUT = Path(".betelgeuze/f2g_f2h_surface_preflight.local.json")
SCHEMA_VERSION = "f2g-f2h-surface-preflight.v1"


JsonPredicate = Callable[[dict[str, Any]], bool]


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get(payload: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _text_contains(path: Path, needles: tuple[str, ...]) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(needle in text for needle in needles)


def _selected_candidate(
    repo_root: Path,
    candidates: tuple[Path, ...],
    *,
    expect_dir: bool = False,
    text_needles: tuple[str, ...] = (),
    json_predicate: JsonPredicate | None = None,
) -> tuple[Path | None, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    for rel_path in candidates:
        path = repo_root / rel_path
        exists = path.is_dir() if expect_dir else path.is_file()
        text_ok = True if not text_needles else _text_contains(path, text_needles)
        json_ok = True
        if json_predicate is not None:
            json_ok = bool(json_predicate(_load_json(path)))
        ready = bool(exists and text_ok and json_ok)
        checks.append(
            {
                "path": rel_path.as_posix(),
                "exists": bool(exists),
                "text_contract_pass": bool(text_ok),
                "json_contract_pass": bool(json_ok),
                "selected": ready,
            }
        )
        if ready:
            return rel_path, checks
    return None, checks


def _receipt_real_per_element_parity(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("status") == "ready"
        and payload.get("uses_real_mgt_model") is True
        and payload.get("promotes_g1_closure") is False
        and payload.get("frame_service_tangent_source") == "real_per_element"
        and _get(payload, "assembled_tangent_parity", "pass") is True
    )


def _receipt_near_null(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("status") == "ready"
        and payload.get("uses_real_mgt_model") is True
        and payload.get("promotes_g1_closure") is False
        and int(_get(payload, "singularity_indicators", "near_null_mode_count", default=0) or 0) > 0
        and isinstance(payload.get("mode_rows"), list)
        and len(payload.get("mode_rows") or []) > 0
    )


def _receipt_support_entity(payload: dict[str, Any]) -> bool:
    return bool(
        _get(payload, "support", "canonical_support_constraint_entity_ready") is True
        and _get(payload, "support", "canonical_elastic_link_entity_ready") is True
        and int(_get(payload, "summary", "unmatched_support_constraint_node_count", default=-1)) == 0
        and int(_get(payload, "summary", "unmatched_elastic_link_node_count", default=-1)) == 0
    )


def _receipt_support_spring(payload: dict[str, Any]) -> bool:
    return bool(
        _get(payload, "support", "authored_support_mask_application_ready") is True
        and _get(payload, "support", "finite_elastic_link_spring_tangent_ready") is True
        and int(_get(payload, "summary", "authored_support_node_count_missing_from_boundary_subsystem", default=-1)) == 0
        and int(_get(payload, "summary", "elastic_link_rows_skipped", default=-1)) == 0
    )


SURFACES: tuple[dict[str, Any], ...] = (
    {
        "surface_id": "implementation_phase1_tree",
        "required_for": ["F2g", "F2h"],
        "description": "Authoritative phase1 implementation tree is present.",
        "candidates": (Path("implementation/phase1"),),
        "expect_dir": True,
        "recovery_action": "Restore implementation/phase1 from the authoritative branch or protected archive.",
    },
    {
        "surface_id": "real_mgt_input",
        "required_for": ["F2g", "F2h"],
        "description": "Real MIDAS MGT input used by the G1 diagnostics is present.",
        "candidates": (
            Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"),
            Path("private_corpus/real_drawings/midas_public_native_mgt_sources/raw/midas_generator_33_github.mgt"),
        ),
        "recovery_action": "Recover the authoritative real MGT input before regenerating any diagnostic receipt.",
    },
    {
        "surface_id": "real_mgt_parsed_model",
        "required_for": ["F2g", "F2h"],
        "description": "Parsed/roundtrip model for the real MGT input is present.",
        "candidates": (
            Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
            Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"),
            Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
        ),
        "recovery_action": "Regenerate the parsed MGT model from the real MGT input with the approved parser.",
    },
    {
        "surface_id": "real_per_element_tangent_implementation",
        "required_for": ["F2g", "F2h"],
        "description": "Implementation path exposes real_per_element assembled-tangent construction.",
        "candidates": (
            Path("implementation/phase1/run_g1_mgt_sparse_direct_physical_line_search_smoke.py"),
            Path("implementation/phase1/run_g1_adaptive_regularization_reference_newton.py"),
        ),
        "text_needles": ("real_per_element",),
        "recovery_action": "Restore the G1 real service tangent implementation; placeholder tangents cannot satisfy this surface.",
    },
    {
        "surface_id": "real_per_element_assembled_tangent_receipt",
        "required_for": ["F2g", "F2h"],
        "description": "Receipt proves real_per_element assembled tangent parity without promoting G1.",
        "candidates": (
            PRODUCTIZATION / "g1_mgt_regularized_assembled_direction_smoke.local.json",
            PRODUCTIZATION / "g1_mgt_real_service_tangent_sparse_direct_smoke.local.json",
        ),
        "json_predicate": _receipt_real_per_element_parity,
        "recovery_action": "Rerun the non-promoting real-service tangent smoke and preserve assembled_tangent_parity.pass=true.",
    },
    {
        "surface_id": "near_null_mode_packet",
        "required_for": ["F2g"],
        "description": "Near-null mode packet exists with dominant DOF/node rows.",
        "candidates": (PRODUCTIZATION / "g1_null_space_mode_audit.local.json",),
        "json_predicate": _receipt_near_null,
        "recovery_action": "Rerun the non-promoting null-space mode audit to materialize dominant DOF/node rows.",
    },
    {
        "surface_id": "support_elastic_entity_context",
        "required_for": ["F2g"],
        "description": "Typed support and elastic-link entity context is present.",
        "candidates": (PRODUCTIZATION / "mgt_boundary_entity_support_receipt.json",),
        "json_predicate": _receipt_support_entity,
        "recovery_action": "Regenerate the boundary entity support receipt from the same real MGT input.",
    },
    {
        "surface_id": "support_elastic_spring_tangent_context",
        "required_for": ["F2g"],
        "description": "Support masks and finite elastic-link spring tangent context are present.",
        "candidates": (PRODUCTIZATION / "mgt_boundary_spring_tangent_receipt.json",),
        "json_predicate": _receipt_support_spring,
        "recovery_action": "Regenerate the boundary spring tangent receipt and keep global solver closure boundaries visible.",
    },
)


def _build_surface_row(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    selected, checks = _selected_candidate(
        repo_root,
        spec["candidates"],
        expect_dir=bool(spec.get("expect_dir", False)),
        text_needles=tuple(spec.get("text_needles", ())),
        json_predicate=spec.get("json_predicate"),
    )
    ready = selected is not None
    selected_path = repo_root / selected if selected is not None else None
    selected_meta: dict[str, Any] = {}
    if selected_path is not None:
        selected_meta = {
            "path": selected.as_posix(),
            "kind": "dir" if selected_path.is_dir() else "file",
            "sha256": _sha256(selected_path) if selected_path.is_file() else "",
        }
    return {
        "surface_id": spec["surface_id"],
        "required_for": list(spec["required_for"]),
        "description": spec["description"],
        "ready": bool(ready),
        "selected": selected_meta,
        "candidate_checks": checks,
        "blocker": "" if ready else f"missing_or_invalid_surface:{spec['surface_id']}",
        "recovery_action": spec["recovery_action"],
    }


def build_preflight(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    rows = [_build_surface_row(repo_root, spec) for spec in SURFACES]
    blockers = [row["blocker"] for row in rows if row["blocker"]]
    f2g_ready = not blockers
    audit_path = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
    f2h_ready = f2g_ready and (repo_root / audit_path).is_file()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(repo_root),
        "status": "ready" if f2g_ready else "blocked",
        "reason_code": "PASS" if f2g_ready else "ERR_F2G_F2H_SURFACES_MISSING",
        "promotes_g1_closure": False,
        "claim_boundary": "non_promoting_surface_preflight_only",
        "compatibility_note": "Goal brief names tools/build_f2g_f2h_surface_preflight.py; this repo uses scripts/ for local build tools.",
        "summary": {
            "surface_count": len(rows),
            "ready_surface_count": sum(1 for row in rows if row["ready"]),
            "blocker_count": len(blockers),
            "f2g_support_elastic_reconciliation_ready_to_run": bool(f2g_ready),
            "f2h_lightweight_continuation_ready_to_run": bool(f2h_ready),
            "f2h_start_condition": audit_path.as_posix(),
            "f2h_start_condition_present": bool((repo_root / audit_path).is_file()),
        },
        "surfaces": rows,
        "blockers": blockers,
        "next_actions": (
            ["run_f2g_support_elastic_link_reconciliation_audit"]
            if f2g_ready and not f2h_ready
            else ([] if f2g_ready else ["recover_missing_authoritative_surfaces"])
        ),
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_F2h_continuation_without_F2g_audit",
            "no_placeholder_or_dummy_surface_substitution",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_preflight(repo_root=args.repo_root)
    output = args.output_json if args.output_json.is_absolute() else args.repo_root / args.output_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "f2g-f2h-surface-preflight: "
        f"status={payload['status']} "
        f"ready={payload['summary']['ready_surface_count']}/{payload['summary']['surface_count']} "
        f"blockers={payload['summary']['blocker_count']} "
        f"f2h_ready={payload['summary']['f2h_lightweight_continuation_ready_to_run']}"
    )
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
