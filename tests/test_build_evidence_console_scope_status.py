from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_evidence_console_scope_status.py"
SPEC = importlib.util.spec_from_file_location("build_evidence_console_scope_status", SCRIPT_PATH)
assert SPEC is not None
scope_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(scope_status)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scope_text() -> str:
    return "\n".join(
        [
            "Evidence Console first scope:",
            "- case list",
            "- source/provenance inspector",
            "- reference vs engine comparison",
            "- residual audit",
            "- worst member/story",
            "- PASS/REVIEW/FAIL reviewer decision",
            "- reproduce bundle export",
            "Deferred full GUI surfaces:",
            "- full project dashboard",
            "- model editor",
            "- accounts/permissions",
            "- collaboration",
            "- licensing",
        ]
    )


def _inputs(tmp_path: Path, *, customer_shadow_pass: bool) -> dict[str, Path]:
    customer_summary = {
        "completed_shadow_case_count": 3 if customer_shadow_pass else 0,
        "min_completed_shadow_cases": 3,
    }
    return {
        "p0_status": _write_json(tmp_path / "p0.json", {"p0_closed": True, "status": "closed"}),
        "p1_readiness": _write_json(tmp_path / "p1.json", {"status": "ready", "p1_execution_unblocked": True}),
        "p1_benchmark_breadth": _write_json(tmp_path / "breadth.json", {"status": "ready"}),
        "real_project_status": _write_json(tmp_path / "real.json", {"contract_pass": True}),
        "customer_shadow_status": _write_json(
            tmp_path / "shadow.json",
            {
                "contract_pass": customer_shadow_pass,
                "summary": customer_summary,
                "blockers": [] if customer_shadow_pass else ["completed_shadow_case_count_below_minimum"],
            },
        ),
    }


def test_evidence_console_scope_blocks_until_customer_shadow_ready(tmp_path: Path) -> None:
    payload = scope_status.build_status(
        scope_source=_write_text(tmp_path / "scope.md", _scope_text()),
        **_inputs(tmp_path, customer_shadow_pass=False),
    )

    assert payload["scope_contract_pass"] is True
    assert payload["launch_ready"] is False
    assert payload["contract_pass"] is False
    assert payload["summary"]["evidence_console_feature_pass_count"] == 7
    assert payload["summary"]["deferred_gui_surface_pass_count"] == 5
    assert payload["summary"]["launch_prerequisite_pass_count"] == 4
    assert "launch_prerequisite_blocked:customer_shadow_completed_project_cases_ready" in payload["blockers"]


def test_evidence_console_scope_passes_when_prerequisites_are_ready(tmp_path: Path) -> None:
    payload = scope_status.build_status(
        scope_source=_write_text(tmp_path / "scope.md", _scope_text()),
        **_inputs(tmp_path, customer_shadow_pass=True),
    )

    assert payload["contract_pass"] is True
    assert payload["launch_ready"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["blockers"] == []


def test_evidence_console_scope_blocks_missing_scope_and_prohibited_claim(tmp_path: Path) -> None:
    scope = _scope_text().replace("- residual audit\n", "") + "\nfull_gui_ready=true\n"
    payload = scope_status.build_status(
        scope_source=_write_text(tmp_path / "scope.md", scope),
        **_inputs(tmp_path, customer_shadow_pass=True),
    )

    assert payload["scope_contract_pass"] is False
    assert payload["contract_pass"] is False
    assert "evidence_console_feature_missing:residual_audit" in payload["blockers"]
    assert "prohibited_first_scope_claim_present:full_gui_ready_true" in payload["blockers"]


def test_evidence_console_scope_scans_claim_boundary_docs_for_prohibited_claims(
    tmp_path: Path,
) -> None:
    readme = _write_text(tmp_path / "README.md", "model_editor_ready=true\n")
    current_state = _write_text(tmp_path / "current-state.md", "collaboration_ready=true\n")

    payload = scope_status.build_status(
        scope_source=_write_text(tmp_path / "scope.md", _scope_text()),
        claim_boundary_docs=(readme, current_state),
        **_inputs(tmp_path, customer_shadow_pass=True),
    )

    assert payload["scope_contract_pass"] is False
    assert payload["contract_pass"] is False
    assert payload["summary"]["claim_boundary_docs"] == [str(readme), str(current_state)]
    assert payload["input_checksums"][str(readme)].startswith("sha256:")
    assert payload["input_checksums"][str(current_state)].startswith("sha256:")
    assert "prohibited_first_scope_claim_present:model_editor_ready_true" in payload["blockers"]
    assert "prohibited_first_scope_claim_present:collaboration_ready_true" in payload["blockers"]
