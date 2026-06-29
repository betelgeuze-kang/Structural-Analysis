from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_f2h_lightweight_continuation_status.py"
SPEC = importlib.util.spec_from_file_location("build_f2h_lightweight_continuation_status", SCRIPT_PATH)
assert SPEC and SPEC.loader
status_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status_module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_f2h_status_passes_for_required_sequence(tmp_path: Path) -> None:
    continuation = tmp_path / "continuation.json"
    audit = tmp_path / "audit.json"
    _write_json(
        continuation,
        {
            "load_steps_requested": [0.1, 0.2, 0.4],
            "max_converged_load_scale": 0.4,
            "first_failed_load_scale": None,
            "step_results": [
                {"load_step": 0.1, "ready": True, "converged": True, "residual_inf_n": 0.01, "relative_increment": 1e-5},
                {"load_step": 0.2, "ready": True, "converged": True, "residual_inf_n": 0.02, "relative_increment": 2e-5},
                {"load_step": 0.4, "ready": True, "converged": True, "residual_inf_n": 0.03, "relative_increment": 3e-5},
            ],
        },
    )
    _write_json(
        audit,
        {
            "status": "ready",
            "near_null_context": {"near_null_mode_count": 8},
            "summary": {
                "dominant_dof_row_count": 64,
                "direct_support_member_count": 0,
                "direct_elastic_link_endpoint_count": 0,
            },
        },
    )

    payload = status_module.build_status(repo_root=tmp_path, continuation_path=continuation, f2g_audit_path=audit)

    assert payload["status"] == "ready"
    assert payload["summary"]["required_sequence_proven"] is True
    assert payload["summary"]["load_scale_monotonic_increasing"] is True
    assert payload["mode_comparison"]["baseline_near_null_mode_count"] == 8
    assert payload["promotes_g1_closure"] is False


def test_f2h_status_blocks_on_wrong_sequence(tmp_path: Path) -> None:
    continuation = tmp_path / "continuation.json"
    audit = tmp_path / "audit.json"
    _write_json(
        continuation,
        {
            "load_steps_requested": [0.1, 0.4],
            "max_converged_load_scale": 0.4,
            "first_failed_load_scale": None,
            "step_results": [
                {"load_step": 0.1, "ready": True, "converged": True},
                {"load_step": 0.4, "ready": True, "converged": True},
            ],
        },
    )
    _write_json(audit, {"status": "ready"})

    payload = status_module.build_status(repo_root=tmp_path, continuation_path=continuation, f2g_audit_path=audit)

    assert payload["status"] == "blocked"
    assert "required_load_sequence_0p1_0p2_0p4_not_proven" in payload["blockers"]
