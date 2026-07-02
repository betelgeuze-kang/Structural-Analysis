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
    _write_text(
        tmp_path / "scripts/report_pm_release_gate.py",
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json\n"
        ),
    )
    _write_text(
        tmp_path / "tests/test_report_pm_release_gate.py",
        "gpcr_hard_decoy_evidence_surface\n",
    )
    _write_text(
        tmp_path / "tests/test_build_pm_release_blocker_action_register.py",
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json\n"
        ),
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
    pm_gate_script = rows["scripts/report_pm_release_gate.py"]
    pm_gate_test = rows["tests/test_report_pm_release_gate.py"]
    pm_blocker_test = rows["tests/test_build_pm_release_blocker_action_register.py"]
    assert pm_report["reference_role"] == "release_governance_reference"
    assert pm_report["blocking_cleanup_reference"] is False
    assert pm_handoff["reference_role"] == "release_governance_reference"
    assert pm_handoff["blocking_cleanup_reference"] is False
    assert pm_gate_script["reference_role"] == "release_governance_reference"
    assert pm_gate_script["blocking_cleanup_reference"] is False
    assert pm_gate_test["reference_role"] == "release_governance_reference"
    assert pm_gate_test["blocking_cleanup_reference"] is False
    assert pm_blocker_test["reference_role"] == "release_governance_reference"
    assert pm_blocker_test["blocking_cleanup_reference"] is False
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
    assert release_surface_row["reference_path_count"] == 6
    assert release_surface_row["blocking_cleanup_reference_path_count"] == 0
    assert release_surface_row["governance_reference_path_count"] == 6
    assert release_surface_row["cleanup_ready_after_owner_decision"] is True
    assert payload["release_surface_cleanup_blocked_path_count"] == 0
    assert payload["next_reference_cleanup_batch"]["batch_id"] == (
        "cleanup_refs_01_productization_evidence_reference"
    )


def test_cleanup_impact_report_treats_owner_decision_fill_tools_as_scope_governance(
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
    release_surface_path = (
        "implementation/phase1/release_evidence/surface/"
        "gpcr_hard_decoy_evidence_surface.json"
    )
    for path in [
        "scripts/fill_structural_scope_owner_decisions_from_template.py",
        "scripts/fill_structural_scope_release_surface_owner_decisions.py",
        "scripts/merge_structural_scope_owner_decision_batch.py",
        "tests/test_fill_structural_scope_owner_decisions_from_template.py",
        "tests/test_fill_structural_scope_release_surface_owner_decisions.py",
        "tests/test_merge_structural_scope_owner_decision_batch.py",
    ]:
        _write_text(tmp_path / path, f"{release_surface_path}\n")
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    rows = {row["path"]: row for row in payload["reference_rows"]}
    for path in [
        "scripts/fill_structural_scope_owner_decisions_from_template.py",
        "scripts/fill_structural_scope_release_surface_owner_decisions.py",
        "scripts/merge_structural_scope_owner_decision_batch.py",
        "tests/test_fill_structural_scope_owner_decisions_from_template.py",
        "tests/test_fill_structural_scope_release_surface_owner_decisions.py",
        "tests/test_merge_structural_scope_owner_decision_batch.py",
    ]:
        assert rows[path]["reference_role"] == "scope_governance_reference"
        assert rows[path]["blocking_cleanup_reference"] is False
    assert payload["blocking_cleanup_reference_path_count"] == 0
    assert payload["release_surface_cleanup_blocked_path_count"] == 0


def test_cleanup_impact_report_flags_release_freshness_source_boundary_refs(
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
    packet = _owner_review_packet()
    packet["review_rows"].append(
        {
            "path": "implementation/phase1/rust_hip_md3bead_hook/Cargo.toml",
            "path_area": "implementation_phase1",
            "families": ["molecular_dynamics"],
            "matched_tokens": ["md3bead"],
            "owner_review_state": "pending_owner_decision",
        }
    )
    packet["owner_decision_pending_count"] = 3
    _write_json(owner_review, packet)
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/md3bead_soa.py",
        "self reference should be ignored\n",
    )
    _write_text(
        tmp_path / "implementation/phase1/README.md",
        "runtime doc still references md3bead_soa.py\n",
    )
    _write_text(
        tmp_path / "docs/engine-ai-and-comparison-commercialization-gaps.md",
        "engine doc still references md3bead_soa.py\n",
    )
    _write_text(
        tmp_path / ".gitignore",
        "implementation/phase1/rust_hip_md3bead_hook/target/\n",
    )
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    rows = {row["path"]: row for row in payload["blocking_reference_rows"]}
    source_boundary_paths = {
        ".gitignore",
        "docs/engine-ai-and-comparison-commercialization-gaps.md",
        "implementation/phase1/README.md",
    }
    assert set(payload["release_freshness_source_boundary_reference_paths"]) == (
        source_boundary_paths
    )
    assert payload["release_freshness_source_boundary_reference_count"] == 3
    for path in source_boundary_paths:
        assert rows[path]["release_freshness_source_boundary"] is True
        assert rows[path]["cleanup_requires_release_receipt_refresh"] is True

    batch_by_role = {
        batch["reference_role"]: batch
        for batch in payload["blocking_reference_cleanup_batches"]
    }
    assert batch_by_role["implementation_runtime_or_manifest_reference"][
        "release_freshness_source_boundary_paths"
    ] == ["implementation/phase1/README.md"]
    assert batch_by_role["documentation_reference"][
        "release_freshness_source_boundary_paths"
    ] == ["docs/engine-ai-and-comparison-commercialization-gaps.md"]
    assert batch_by_role["other_reference"][
        "release_freshness_source_boundary_paths"
    ] == [".gitignore"]


def test_cleanup_impact_report_ignores_generic_quarantined_basenames(
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
    packet = _owner_review_packet()
    packet["review_rows"] = [
        {
            "path": "implementation/phase1/rust_hip_md3bead_hook/Cargo.toml",
            "path_area": "implementation_phase1",
            "families": ["molecular_dynamics"],
            "matched_tokens": ["md3bead"],
            "owner_review_state": "pending_owner_decision",
        }
    ]
    packet["owner_decision_pending_count"] = 1
    _write_json(owner_review, packet)
    _write_json(origin, _origin_report())
    _write_text(
        tmp_path / "implementation/phase1/rust_hip_md3bead_hook/Cargo.toml",
        "self reference should be ignored\n",
    )
    _write_text(
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "mgt_rust_hip_full_residual_ffi_followup376_probe.json",
        "/repo/implementation/phase1/mgt_hip_full_residual_ffi/Cargo.toml\n",
    )
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    paths = {row["path"] for row in payload["reference_rows"]}
    assert (
        "implementation/phase1/release_evidence/productization/"
        "mgt_rust_hip_full_residual_ffi_followup376_probe.json"
    ) not in paths
    assert payload["blocking_cleanup_reference_path_count"] == 0


def test_cleanup_impact_report_tracks_scope_token_only_rows_without_blocking(
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
        tmp_path / "tests/test_scope_token_guard.py",
        "forbidden_tokens = ('gpcr', 'pocketmd', 'md3bead')\n",
    )
    _git_add(tmp_path)

    payload = impact_report.build_cleanup_impact_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        origin_report_path=origin,
    )

    rows = {row["path"]: row for row in payload["reference_rows"]}
    token_guard = rows["tests/test_scope_token_guard.py"]
    assert token_guard["matched_quarantined_path_count"] == 0
    assert token_guard["owner_decision_dependency"] == "scope_token_review_before_cleanup"
    assert token_guard["blocking_cleanup_reference"] is False
    assert payload["blocking_cleanup_reference_path_count"] == 0
    assert payload["blocking_reference_cleanup_batch_count"] == 0
    assert payload["cleanup_impact_clear"] is True


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
