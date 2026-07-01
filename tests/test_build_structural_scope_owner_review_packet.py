from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_owner_review_packet.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_owner_review_packet", SCRIPT_PATH
)
assert SPEC is not None
owner_review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = owner_review
SPEC.loader.exec_module(owner_review)


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


def test_owner_review_packet_groups_quarantined_paths(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["owner_decision_pending_count"] == 2
    assert payload["release_surface_excluded_path_count"] == 2
    assert payload["unquarantined_non_structural_path_count"] == 0
    assert payload["family_counts"] == {
        "molecular_docking": 1,
        "molecular_dynamics": 1,
    }
    assert payload["path_area_counts"] == {
        "implementation_phase1": 1,
        "productization_evidence": 1,
    }
    rows = {row["path"]: row for row in payload["review_rows"]}
    assert rows["implementation/phase1/md3bead_soa.py"]["structural_release_claim_eligible"] is False
    assert rows["implementation/phase1/md3bead_soa.py"]["owner_review_state"] == "pending_owner_decision"
    assert (
        rows["implementation/phase1/md3bead_soa.py"]["recommended_owner_decision"]
        == "extract_to_molecular_or_science_repository_or_delete_if_obsolete"
    )
    assert (
        rows[
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_product_report.json"
        ]["recommended_owner_decision"]
        == "delete_from_structural_repository_or_extract_only_if_owner_requires_history"
    )


def test_owner_review_packet_blocks_unquarantined_scope_leak(tmp_path: Path) -> None:
    audit_payload = _audit_payload()
    audit_payload["contract_pass"] = False
    audit_payload["blockers"] = ["unquarantined_non_structural_path_count=1"]
    audit_payload["unquarantined_non_structural_rows"] = [
        {
            "path": "scripts/materialize_gpcr_hard_decoy_suite_report.py",
            "git_state": "tracked",
            "path_area": "script",
            "families": ["molecular_docking"],
            "matched_tokens": ["gpcr"],
            "quarantine_status": "unquarantined",
        }
    ]
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _write_json(audit, audit_payload)
    _write_json(manifest, _manifest_payload())

    payload = owner_review.build_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
    )

    assert payload["status"] == "blocked_scope_cleanup"
    assert payload["contract_pass"] is False
    assert payload["evidence_closure_pass"] is False
    assert "unquarantined_non_structural_path_count=1" in payload["blockers"]
    assert payload["unquarantined_non_structural_path_count"] == 1


def test_owner_review_packet_writes_json_and_markdown(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"
    _write_json(audit, _audit_payload())
    _write_json(manifest, _manifest_payload())

    payload = owner_review.write_owner_review_packet(
        repo_root=tmp_path,
        audit_path=audit,
        quarantine_manifest_path=manifest,
        out=out,
        out_md=out_md,
    )

    assert payload["status"] == "ready_for_owner_review"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        owner_review.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Structural Scope Owner Review Packet" in markdown
    assert "implementation/phase1/md3bead_soa.py" in markdown
