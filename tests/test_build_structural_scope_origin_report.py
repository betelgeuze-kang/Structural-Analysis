from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_structural_scope_origin_report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_structural_scope_origin_report", SCRIPT_PATH
)
assert SPEC is not None
origin_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = origin_report
SPEC.loader.exec_module(origin_report)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _owner_review_packet() -> dict:
    return {
        "schema_version": "structural-scope-owner-review-packet.v1",
        "status": "ready_for_owner_review",
        "contract_pass": True,
        "owner_decision_pending_count": 3,
        "review_rows": [
            {
                "path": "implementation/phase1/md3bead_soa.py",
                "path_area": "implementation_phase1",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["md3bead"],
                "owner_review_state": "pending_owner_decision",
                "recommended_owner_decision_primary": (
                    "extract_to_molecular_or_science_repository"
                ),
                "recommended_owner_decision_alternate": (
                    "delete_from_structural_repository"
                ),
                "structural_release_claim_eligible": False,
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
                "recommended_owner_decision_primary": (
                    "delete_from_structural_repository"
                ),
                "recommended_owner_decision_alternate": (
                    "extract_to_molecular_or_science_repository"
                ),
                "structural_release_claim_eligible": False,
            },
            {
                "path": (
                    "implementation/phase1/release_evidence/surface/"
                    "pocketmd_lite_science_product_surface.json"
                ),
                "path_area": "release_surface",
                "families": ["molecular_dynamics"],
                "matched_tokens": ["pocketmd"],
                "owner_review_state": "pending_owner_decision",
                "recommended_owner_decision_primary": (
                    "delete_from_structural_repository"
                ),
                "recommended_owner_decision_alternate": (
                    "extract_to_molecular_or_science_repository"
                ),
                "structural_release_claim_eligible": False,
            },
        ],
    }


def _commit_lookup(_repo_root: Path, path: str) -> dict[str, str]:
    rows = {
        "implementation/phase1/md3bead_soa.py": {
            "commit_sha": "2b655fe3abcdef",
            "commit_short_sha": "2b655fe3",
            "commit_date": "2026-04-26",
            "commit_subject": "Import structural analysis workbench implementation",
        },
        (
            "implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json"
        ): {
            "commit_sha": "805535fcabcdef",
            "commit_short_sha": "805535fc",
            "commit_date": "2026-06-30",
            "commit_subject": "Add locked H-Bond and GPCR evidence surfaces",
        },
        (
            "implementation/phase1/release_evidence/surface/"
            "pocketmd_lite_science_product_surface.json"
        ): {
            "commit_sha": "01e6fe1babcdef",
            "commit_short_sha": "01e6fe1b",
            "commit_date": "2026-06-30",
            "commit_subject": "Materialize PocketMD Lite product surface",
        },
    }
    return rows[path]


def test_origin_report_groups_scope_introduction_waves(tmp_path: Path) -> None:
    owner_review = tmp_path / "owner_review.json"
    _write_json(owner_review, _owner_review_packet())

    payload = origin_report.build_origin_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        commit_lookup=_commit_lookup,
    )

    assert payload["status"] == "ready_for_owner_review_origin_evidence"
    assert payload["contract_pass"] is True
    assert payload["origin_evidence_complete"] is True
    assert payload["quarantined_path_count"] == 3
    assert payload["release_surface_origin_path_count"] == 2
    assert payload["origin_wave_counts"] == {
        "initial_bulk_import_with_md3bead_runtime": 1,
        "pocketmd_release_surface_materialization": 1,
        "science_release_surface_seed": 1,
    }
    assert payload["path_area_counts"] == {
        "implementation_phase1": 1,
        "release_surface": 2,
    }
    release_paths = {
        row["path"]: row for row in payload["release_surface_origin_rows"]
    }
    assert release_paths[
        "implementation/phase1/release_evidence/surface/"
        "gpcr_hard_decoy_evidence_surface.json"
    ]["recommended_owner_decision_primary"] == "delete_from_structural_repository"
    assert "tracked molecular runtime" in payload["root_cause_summary"]


def test_origin_report_blocks_when_git_origin_is_missing(tmp_path: Path) -> None:
    owner_review = tmp_path / "owner_review.json"
    packet = _owner_review_packet()
    packet["review_rows"] = packet["review_rows"][:1]
    _write_json(owner_review, packet)

    payload = origin_report.build_origin_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        commit_lookup=lambda _repo_root, _path: {
            "commit_sha": "",
            "commit_short_sha": "",
            "commit_date": "",
            "commit_subject": "",
        },
    )

    assert payload["status"] == "blocked_origin_report"
    assert payload["contract_pass"] is False
    assert payload["missing_origin_count"] == 1
    assert payload["blockers"] == ["origin_commit_missing_count=1"]


def test_origin_report_markdown_surfaces_release_first_batch(tmp_path: Path) -> None:
    owner_review = tmp_path / "owner_review.json"
    out = tmp_path / "origin.json"
    out_md = tmp_path / "origin.md"
    _write_json(owner_review, _owner_review_packet())

    payload = origin_report.write_origin_report(
        repo_root=tmp_path,
        owner_review_packet_path=owner_review,
        out=out,
        out_md=out_md,
    )

    markdown = out_md.read_text(encoding="utf-8")
    assert payload["summary_line"] in markdown
    assert "## Origin Waves" in markdown
    assert "## Release Surface First" in markdown
    assert "gpcr_hard_decoy_evidence_surface.json" in markdown
