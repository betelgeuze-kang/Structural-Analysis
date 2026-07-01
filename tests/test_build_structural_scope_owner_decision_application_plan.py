from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_owner_decision_application_plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_owner_decision_application_plan", SCRIPT_PATH
)
assert SPEC is not None
application_plan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = application_plan
SPEC.loader.exec_module(application_plan)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _audit_payload() -> dict:
    return {
        "schema_version": "structural-scope-contamination-audit.v1",
        "status": "quarantined",
        "contract_pass": True,
        "blockers": [],
        "quarantined_non_structural_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "git_state": "tracked",
                "path_area": "implementation_phase1",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["md3bead"],
                "quarantine_status": "quarantined",
                "excluded_from_structural_release_surface": True,
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json"
                ),
                "git_state": "tracked",
                "path_area": "productization_evidence",
                "families": ["molecular_docking"],
                "matched_tokens": ["gpcr"],
                "quarantine_status": "quarantined",
                "excluded_from_structural_release_surface": True,
            },
        ],
        "unquarantined_non_structural_rows": [],
    }


def _manifest_payload() -> dict:
    return {
        "schema_version": "structural-scope-quarantine-manifest.v1",
        "status": "active",
        "paths": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "excluded_from_structural_release_surface": True,
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json"
                ),
                "excluded_from_structural_release_surface": True,
            },
        ],
    }


def _decision_row(path: str, decision: str, index: int) -> dict:
    return {
        "path": path,
        "owner_decision": decision,
        "owner_identity": "scope-owner",
        "owner_role": "product_owner",
        "decision_timestamp_utc": "2026-07-02T00:00:00Z",
        "evidence_reference": f"owner-review://scope-cleanup/{index:03d}",
    }


def _decision_payload(*decisions: tuple[str, str]) -> dict:
    return {
        "schema_version": application_plan.owner_review.DECISION_SCHEMA_VERSION,
        "decision_rows": [
            _decision_row(path, decision, index + 1)
            for index, (path, decision) in enumerate(decisions)
        ],
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())
    return audit, manifest


def test_application_plan_waits_for_owner_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
    )

    assert payload["status"] == "pending_owner_decisions"
    assert payload["contract_pass"] is True
    assert payload["application_ready"] is False
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 2
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["plan_blockers"] == ["owner_decision_pending_count=2"]
    assert len(payload["pending_owner_decision_rows"]) == 2


def test_application_plan_routes_delete_and_extract_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            ("implementation/phase1/md3bead_soa.py", "extract_to_molecular_or_science_repository"),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "delete_from_structural_repository",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_cleanup_application"
    assert payload["application_ready"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 2
    assert payload["delete_decision_count"] == 1
    assert payload["extract_decision_count"] == 1
    assert len(payload["cleanup_rows"]) == 2
    rows = {row["path"]: row for row in payload["cleanup_rows"]}
    assert rows["implementation/phase1/md3bead_soa.py"]["required_action"] == (
        "extract_elsewhere_then_remove_from_structural_repository"
    )
    assert rows[
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json"
    ]["suggested_git_rm_args"] == [
        "git",
        "rm",
        "--",
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_product_report.json",
    ]


def test_application_plan_accepts_owner_decision_csv(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.csv"
    decisions.write_text(
        "\n".join(
            [
                ",".join(application_plan.owner_review.OWNER_DECISION_COLUMNS),
                (
                    "row-1,implementation/phase1/md3bead_soa.py,"
                    "implementation_phase1,molecular_dynamics,md3bead,"
                    "extract_to_molecular_or_science_repository_or_delete_if_obsolete,"
                    "extract_to_molecular_or_science_repository,scope-owner,"
                    "product_owner,2026-07-02T00:00:00Z,"
                    "owner-review://scope-cleanup/001"
                ),
                (
                    "row-2,"
                    "implementation/phase1/release_evidence/productization/"
                    "gpcr_hard_decoy_product_report.json,productization_evidence,"
                    "molecular_docking,gpcr,"
                    "delete_from_structural_repository_or_extract_only_if_owner_requires_history,"
                    "delete_from_structural_repository,scope-owner,product_owner,"
                    "2026-07-02T00:00:00Z,"
                    "owner-review://scope-cleanup/002"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "ready_for_cleanup_application"
    assert payload["application_ready"] is True
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 2


def test_application_plan_closes_retain_exception_decisions(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    decisions = tmp_path / "owner_decisions.json"
    _write_json(
        decisions,
        _decision_payload(
            (
                "implementation/phase1/md3bead_soa.py",
                "retain_quarantined_with_signed_owner_exception",
            ),
            (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_product_report.json",
                "retain_quarantined_with_signed_owner_exception",
            ),
        ),
    )

    payload = application_plan.build_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=decisions,
    )

    assert payload["status"] == "complete"
    assert payload["application_ready"] is False
    assert payload["evidence_closure_pass"] is True
    assert payload["owner_decision_pending_count"] == 0
    assert payload["post_decision_cleanup_pending_count"] == 0
    assert payload["retain_quarantined_exception_count"] == 2
    assert payload["cleanup_rows"] == []
    assert len(payload["retain_exception_rows"]) == 2


def test_application_plan_writes_json_and_markdown(tmp_path: Path) -> None:
    audit, manifest = _write_inputs(tmp_path)
    out = tmp_path / "plan.json"
    out_md = tmp_path / "plan.md"

    payload = application_plan.write_application_plan(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        owner_decisions_path=tmp_path / "missing_decisions.json",
        out=out,
        out_md=out_md,
    )

    assert payload["status"] == "pending_owner_decisions"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        application_plan.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Structural Scope Owner Decision Application Plan" in markdown
    assert "owner_decision_pending_count=2" in markdown
