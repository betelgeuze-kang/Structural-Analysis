#!/usr/bin/env python3
"""Honest checklist for what is required before claiming GPU Newton terminal solve."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_gpu_solver_claim_receipt import build_gpu_solver_claim_receipt


SCHEMA_VERSION = "gpu-newton-certification-checklist.v1"

REQUIRED_EVIDENCE = [
    "Host Newton reference solve on identical optimization story fingerprint",
    "Step-by-step Newton residual log with device attribution per iteration",
    "Jacobian assembly and Newton updates on GPU without CPU fallback",
    "Top displacement within tolerance vs host reference and production GPU main-loop",
    "Third-party or licensed-engineer review receipt for external marketing claims",
]


def build_gpu_newton_certification_checklist(
    *,
    state_npz_path: Path,
    terminal_certification_path: Path | None = None,
) -> dict[str, Any]:
    receipt = build_gpu_solver_claim_receipt(
        state_npz_path=state_npz_path,
        terminal_certification_path=terminal_certification_path,
    )
    residency = bool(receipt.get("gpu_mainloop_residency_observed"))
    proven = bool(receipt.get("gpu_newton_terminal_proven"))
    cert_inner = receipt.get("terminal_certification") if isinstance(receipt.get("terminal_certification"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "certified" if proven else "not_certified",
        "gpu_newton_terminal_proven": proven,
        "gpu_mainloop_residency_observed": residency,
        "claim_label": receipt.get("claim_label"),
        "marketing_safe_wording": receipt.get("marketing_safe_wording"),
        "required_evidence_before_terminal_claim": REQUIRED_EVIDENCE,
        "observed_receipt": receipt,
        "terminal_certification": cert_inner,
        "certification_blockers": [] if proven else ["gpu_newton_terminal_not_proven"],
    }
