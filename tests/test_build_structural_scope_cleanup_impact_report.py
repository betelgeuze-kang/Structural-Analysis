from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_cleanup_impact_report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_cleanup_impact_report", SCRIPT_PATH
)
assert SPEC is not None
impact_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = impact_report
SPEC.loader.exec_module(impact_report)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _init_git_repo(path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "test@example.invalid"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=path)


def _git_add(path: Path) -> None:
    subprocess.check_call(["git", "add", "."], cwd=path)


def _owner_review_packet() -> dict:
    return {
        "schema_version": "structural-scope-owner-review-packet.v1",
        "status": "ready_for_owner_review",
        "contract_pass": True,
        "owner_decision_pending_count": 2,
        "review_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "path_area": "implementation_phase1",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["md3bead"],
                "owner_review_state": "pending_owner_decision",
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/surface/"
                    "gpcr_hard_decoy_evidence_surface.json"
                ),
                "path_area": "release_surface",
                "families": ["molecular_docking"],
                "matched_tokens": ["gpcr"],
                "owner_review_state": "pending_owner_decision",
            },
        ],
    }


def _origin_report() -> dict:
    return {
        "schema_version": "structural-scope-origin-report.v1",
        "status": "ready_for_owner_review_origin_evidence",
        "contract_pass": True,
    }


def test_cleanup_impact_report_classifies_blocking_and_governance_refs(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    owner_review = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_owner_review_packet.json"
    )
    origin = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_origin_report.json"
    )
    _write_json(owner_review, _owner_review_packet())
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/md3bead_soa.py",
        "self reference should be ignored\n",
    )
    _write_text(
        tmp_path / "implementation/phase1/native_runtime_artifact_manifest.json",
        '{"path": "implementation/phase1/md3bead_soa.py"}\n',
    )
    _write_text(
        tmp_path / "docs/scope-note.md",
        "Remove gpcr_hard_decoy_evidence_surface.json after owner review.\n",
    )
    _write_text(
        tmp_path / "scripts/build_structural_scope_owner_review_packet.py",
        "implementation/phase1/md3bead_soa.py\n",
    )
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    assert payload["status"] == "blocked_cleanup_impact"
    assert payload["cleanup_impact_clear"] is False
    assert payload["reference_path_count"] == 4
    assert payload["blocking_cleanup_reference_path_count"] == 2
    assert payload["governance_reference_path_count"] == 2
    assert payload["blocking_reference_role_counts"] == {
        "documentation_reference": 1,
        "implementation_runtime_or_manifest_reference": 1,
    }
    assert payload["blocking_reference_cleanup_batch_count"] == 2
    assert payload["next_reference_cleanup_batch"]["batch_id"] == (
        "cleanup_refs_02_implementation_runtime_or_manifest_reference"
    )
    assert payload["blocking_reference_cleanup_action_counts"] == {
        "remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts": 1,
        "rewrite_structural_docs_to_scope_boundary_only": 1,
    }
    release_surface_rows = {
        row["path"]: row for row in payload["release_surface_cleanup_impact_rows"]
    }
    release_surface_row = release_surface_rows[
        "implementation/phase1/release_evidence/surface/"
        "gpcr_hard_decoy_evidence_surface.json"
    ]
    assert release_surface_row["reference_path_count"] == 2
    assert release_surface_row["blocking_cleanup_reference_path_count"] == 1
    assert release_surface_row["governance_reference_path_count"] == 1
    assert release_surface_row["cleanup_ready_after_owner_decision"] is False
    assert release_surface_row["blocking_reference_paths"] == ["docs/scope-note.md"]
    assert payload["release_surface_cleanup_blocked_path_count"] == 1
    assert "blocking_cleanup_reference_path_count=2" in payload["blockers"]


def test_cleanup_impact_report_treats_pm_scope_tracking_as_release_governance(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    owner_review = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_owner_review_packet.json"
    )
    origin = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_origin_report.json"
    )
    _write_json(owner_review, _owner_review_packet())
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/md3bead_soa.py",
        "self reference should be ignored\n",
    )
    _write_text(
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "pm_release_gate_report.json",
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json\n"
        ),
    )
    _write_text(
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "pm_release_gate_reviewer_handoff.md",
        "Owner decision pending for gpcr_hard_decoy_evidence_surface.json.\n",
    )
    _write_text(
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "public_benchmark_source_of_truth.json",
        "implementation/phase1/md3bead_soa.py\n",
    )
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    rows = {row["path"]: row for row in payload["reference_rows"]}
    pm_report = rows[
        "implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
    ]
    pm_handoff = rows[
        "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.md"
    ]
    public_benchmark = rows[
        "implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json"
    ]
    assert pm_report["reference_role"] == "release_governance_reference"
    assert pm_report["blocking_cleanup_reference"] is False
    assert pm_handoff["reference_role"] == "release_governance_reference"
    assert pm_handoff["blocking_cleanup_reference"] is False
    assert public_benchmark["reference_role"] == "productization_evidence_reference"
    assert public_benchmark["blocking_cleanup_reference"] is True
    assert payload["blocking_reference_role_counts"] == {
        "productization_evidence_reference": 1,
    }
    release_surface_rows = {
        row["path"]: row for row in payload["release_surface_cleanup_impact_rows"]
    }
    release_surface_row = release_surface_rows[
        "implementation/phase1/release_evidence/surface/"
        "gpcr_hard_decoy_evidence_surface.json"
    ]
    assert release_surface_row["reference_path_count"] == 3
    assert release_surface_row["blocking_cleanup_reference_path_count"] == 0
    assert release_surface_row["governance_reference_path_count"] == 3
    assert release_surface_row["cleanup_ready_after_owner_decision"] is True
    assert payload["release_surface_cleanup_blocked_path_count"] == 0
    assert payload["next_reference_cleanup_batch"]["batch_id"] == (
        "cleanup_refs_01_productization_evidence_reference"
    )


def test_cleanup_impact_report_can_be_clear_except_owner_decisions(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    owner_review = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_owner_review_packet.json"
    )
    origin = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_origin_report.json"
    )
    _write_json(owner_review, _owner_review_packet())
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/md3bead_soa.py",
        "self reference should be ignored\n",
    )
    _write_text(tmp_path / "README.md", "Structural analysis only.\n")
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    assert payload["status"] == "blocked_cleanup_impact"
    assert payload["cleanup_impact_clear"] is True
    assert payload["reference_path_count"] == 1
    assert payload["blocking_cleanup_reference_path_count"] == 0
    assert payload["blocking_reference_cleanup_batch_count"] == 0
    assert payload["next_reference_cleanup_batch"] == {}
    assert payload["blockers"] == ["owner_decision_pending_count=2"]


def test_cleanup_impact_report_cli_writes_markdown(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    owner_review = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_owner_review_packet.json"
    )
    origin = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "structural_scope_origin_report.json"
    )
    out = tmp_path / "impact.json"
    out_md = tmp_path / "impact.md"
    _write_json(owner_review, _owner_review_packet())
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/native_runtime_artifact_manifest.json",
        "md3bead_soa.py\n",
    )
    _git_add(tmp_path)

    payload = impact_report.write_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
        out=out,
        out_md=out_md,
    )

    markdown = out_md.read_text(encoding="utf-8")
    assert payload["summary_line"] in markdown
    assert "## Cleanup Batches" in markdown
    assert "## Release Surface First Impact" in markdown
    assert "## Blocking References" in markdown
    assert "native_runtime_artifact_manifest.json" in markdown
