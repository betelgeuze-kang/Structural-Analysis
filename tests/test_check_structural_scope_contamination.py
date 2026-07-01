from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_structural_scope_contamination.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_structural_scope_contamination", SCRIPT_PATH
)
assert SPEC is not None
scope_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = scope_audit
SPEC.loader.exec_module(scope_audit)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def _tracked(path: Path, text: str = "fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scope_audit_blocks_tracked_molecular_product_paths(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "src" / "structural_analysis" / "solver.py")
    _tracked(tmp_path / "scripts" / "score_symmetry_aware_ligand_rmsd.py")
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "pocketmd_lite_contract.json",
        "{}\n",
    )
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "surface"
        / "gpcr_hard_decoy_evidence_surface.json",
        "{}\n",
    )
    _git("add", ".", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert payload["non_structural_path_count"] == 3
    assert payload["non_structural_tracked_path_count"] == 3
    assert payload["non_structural_untracked_path_count"] == 0
    assert payload["git_state_counts"] == {"tracked": 3}
    assert payload["path_area_counts"] == {
        "productization_evidence": 1,
        "release_surface": 1,
        "script": 1,
    }
    assert payload["quarantined_non_structural_path_count"] == 0
    assert payload["unquarantined_non_structural_path_count"] == 3
    assert "unquarantined_non_structural_path_count=3" in payload["blockers"]
    assert "unquarantined_non_structural_git_tracked_path_count=3" in payload["blockers"]
    assert "unquarantined_non_structural_release_evidence_path_count=2" in payload["blockers"]
    assert "unquarantined_non_structural_script_path_count=1" in payload["blockers"]
    paths = {row["path"] for row in payload["non_structural_rows"]}
    assert "src/structural_analysis/solver.py" not in paths
    assert "scripts/score_symmetry_aware_ligand_rmsd.py" in paths
    assert {row["quarantine_status"] for row in payload["non_structural_rows"]} == {
        "unquarantined"
    }


def test_scope_audit_does_not_block_ui_docking_homonym(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "scripts" / "verify-structure-viewer-callout-docking.mjs")
    _git("add", ".", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["contract_pass"] is True
    assert payload["status"] == "pass"
    assert payload["non_structural_rows"] == []


def test_scope_audit_blocks_molecular_public_benchmark_templates(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "public_benchmark_pose_rows_template.csv",
        "case_id,pose_success_metric,protein_structure_path\n"
        "casf_pdbbind_subset_001,symmetry_aware_ligand_rmsd_angstrom,protein.pdb\n",
    )
    _tracked(
        tmp_path / "scripts" / "materialize_public_benchmark_posebusters_validity_packet.py"
    )
    _tracked(
        tmp_path / "tests" / "test_materialize_public_benchmark_enrichment_scorecard.py"
    )
    _git("add", ".", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["non_structural_path_count"] == 3
    assert payload["unquarantined_non_structural_path_count"] == 3
    assert payload["path_area_counts"] == {
        "productization_evidence": 1,
        "script": 1,
        "test": 1,
    }
    paths = {row["path"] for row in payload["non_structural_rows"]}
    assert (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_pose_rows_template.csv"
    ) in paths
    assert "scripts/materialize_public_benchmark_posebusters_validity_packet.py" in paths
    assert "tests/test_materialize_public_benchmark_enrichment_scorecard.py" in paths


def test_scope_audit_counts_untracked_molecular_paths(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "src" / "structural_analysis" / "solver.py")
    _tracked(tmp_path / "scratch" / "pocketmd_lite_probe.json", "{}\n")
    _git("add", "src/structural_analysis/solver.py", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["non_structural_path_count"] == 1
    assert payload["non_structural_tracked_path_count"] == 0
    assert payload["non_structural_untracked_path_count"] == 1
    assert payload["git_state_counts"] == {"untracked": 1}
    assert payload["non_structural_rows"][0]["git_state"] == "untracked"
    assert "unquarantined_non_structural_git_untracked_path_count=1" in payload["blockers"]

    tracked_only = scope_audit.build_audit(
        repo_root=tmp_path,
        include_untracked=False,
    )
    assert tracked_only["contract_pass"] is True
    assert tracked_only["non_structural_path_count"] == 0


def test_scope_audit_quarantines_exact_manifest_paths(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "pocketmd_lite_contract.json",
        "{}\n",
    )
    _tracked(tmp_path / "scripts" / "score_symmetry_aware_ligand_rmsd.py")
    _git("add", ".", cwd=tmp_path)
    manifest = tmp_path / "scope_quarantine.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": scope_audit.QUARANTINE_SCHEMA_VERSION,
                "status": "active",
                "paths": [
                    {
                        "path": (
                            "implementation/phase1/release_evidence/productization/"
                            "pocketmd_lite_contract.json"
                        ),
                        "excluded_from_structural_release_surface": True,
                    },
                    {
                        "path": "scripts/score_symmetry_aware_ligand_rmsd.py",
                        "excluded_from_structural_release_surface": True,
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = scope_audit.build_audit(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
    )

    assert payload["status"] == "quarantined"
    assert payload["contract_pass"] is True
    assert payload["non_structural_path_count"] == 2
    assert payload["quarantined_non_structural_path_count"] == 2
    assert payload["unquarantined_non_structural_path_count"] == 0
    assert payload["blockers"] == []
    assert {row["quarantine_status"] for row in payload["non_structural_rows"]} == {
        "quarantined"
    }


def test_scope_audit_blocks_release_surface_text_leak(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "src" / "structural_analysis" / "solver.py")
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "surface"
        / "product_capabilities_surface.json",
        json.dumps(
            {
                "surface_id": "product_capabilities_surface",
                "capability_rows": [
                    {"capability_id": "pocketmd_lite_top_k_refinement"}
                ],
            }
        )
        + "\n",
    )
    _git("add", ".", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["non_structural_path_count"] == 0
    assert payload["release_surface_text_guard_path_count"] == 1
    assert payload["release_surface_text_leak_path_count"] == 1
    assert payload["release_surface_text_leak_rows"] == [
        {
            "path": (
                "implementation/phase1/release_evidence/surface/"
                "product_capabilities_surface.json"
            ),
            "read_error": "",
            "matched_tokens": ["pocketmd"],
        }
    ]
    assert (
        "release_surface_text_non_structural_token_path_count=1"
        in payload["blockers"]
    )
    assert payload["next_actions"] == [
        "remove_non_structural_tokens_from_structural_release_surface_outputs",
        "regenerate_release_freshness_pm_snapshot_after_scope_cleanup",
    ]


def test_scope_audit_blocks_dynamic_release_surface_text_leak(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "src" / "structural_analysis" / "solver.py")
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "surface"
        / "structural_solver_claim_surface.json",
        json.dumps(
            {
                "surface_id": "structural_solver_claim_surface",
                "claim_boundary": "No GPCR hard-decoy claims here.",
            }
        )
        + "\n",
    )
    _git("add", ".", cwd=tmp_path)

    payload = scope_audit.build_audit(repo_root=tmp_path)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["non_structural_path_count"] == 0
    assert payload["release_surface_text_guard_path_count"] == 1
    assert payload["release_surface_text_leak_path_count"] == 1
    assert payload["release_surface_text_leak_rows"][0] == {
        "path": (
            "implementation/phase1/release_evidence/surface/"
            "structural_solver_claim_surface.json"
        ),
        "read_error": "",
        "matched_tokens": ["gpcr"],
    }


def test_scope_audit_skips_quarantined_release_surface_text_guard(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "surface"
        / "gpcr_hard_decoy_evidence_surface.json",
        json.dumps({"surface_id": "gpcr_hard_decoy_evidence_surface"})
        + "\n",
    )
    _git("add", ".", cwd=tmp_path)
    manifest = tmp_path / "scope_quarantine.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": scope_audit.QUARANTINE_SCHEMA_VERSION,
                "status": "active",
                "paths": [
                    {
                        "path": (
                            "implementation/phase1/release_evidence/surface/"
                            "gpcr_hard_decoy_evidence_surface.json"
                        ),
                        "excluded_from_structural_release_surface": True,
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = scope_audit.build_audit(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
    )

    assert payload["status"] == "quarantined"
    assert payload["contract_pass"] is True
    assert payload["release_surface_text_leak_path_count"] == 0
    assert payload["release_surface_text_guard_skipped_quarantined_path_count"] == 1
    assert payload["release_surface_text_guard_skipped_quarantined_paths"] == [
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json"
        )
    ]


def test_scope_audit_writes_json_and_markdown(tmp_path: Path) -> None:
    _git("init", cwd=tmp_path)
    _tracked(tmp_path / "implementation" / "phase1" / "md3bead_soa.py")
    _git("add", ".", cwd=tmp_path)

    out = tmp_path / "out" / "audit.json"
    out_md = tmp_path / "out" / "audit.md"
    payload = scope_audit.write_audit(repo_root=tmp_path, out=out, out_md=out_md)

    assert payload["status"] == "blocked"
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "blocked"
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Structural Scope Contamination Audit" in markdown
    assert "| Git State | Count |" in markdown
    assert "implementation/phase1/md3bead_soa.py" in markdown
