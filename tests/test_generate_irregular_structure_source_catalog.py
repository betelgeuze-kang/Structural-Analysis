from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from implementation.phase1.generate_irregular_structure_source_catalog import (
    CATALOG_VERSION,
    DEFAULT_PRIORITY_PATH,
    SOURCE_ROWS,
    build_catalog,
)


SCRIPT = Path("implementation/phase1/generate_irregular_structure_source_catalog.py")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def test_build_catalog_uses_priority_families_and_local_remote_split() -> None:
    catalog, triage = build_catalog(DEFAULT_PRIORITY_PATH)

    assert catalog["schema_version"] == "1.0"
    assert catalog["catalog_version"] == CATALOG_VERSION
    assert catalog["summary"]["family_count"] == 20
    assert catalog["summary"]["source_record_count"] == len(SOURCE_ROWS)
    assert catalog["summary"]["local_ready_count"] >= 7
    assert catalog["summary"]["remote_candidate_count"] >= 10

    family_ids = [row["id"] for row in catalog["structure_families"]]
    assert family_ids[:3] == [
        "transfer_podium_tower",
        "soft_story_podium_tower",
        "torsionally_eccentric_core_tower",
    ]
    assert "curved_plan_bridge_torsion" in family_ids

    bridge_rows = [row for row in catalog["source_records"] if row["family_id"] == "curved_plan_bridge_torsion"]
    assert len(bridge_rows) >= 3
    assert any(row["primary_format"] == "mgt" for row in bridge_rows)
    assert any(row["primary_format"] == "mcb" for row in bridge_rows)

    rows_by_id = {row["source_id"]: row for row in catalog["source_records"]}
    assert rows_by_id["transfer_podium_tower_proxy_local"]["source_kind"] == "repo_local_bridged"
    assert rows_by_id["transfer_podium_tower_proxy_local"]["evidence_class"] == "repo_local_bridged_graph"
    assert rows_by_id["transfer_podium_tower_proxy_local"]["metadata"]["bridge_report_path"].endswith("bridge_report.json")
    assert rows_by_id["soft_story_podium_tower_proxy_local"]["source_kind"] == "repo_local_bridged"
    assert rows_by_id["soft_story_podium_tower_proxy_local"]["evidence_class"] == "repo_local_bridged_graph"
    assert rows_by_id["offset_core_megatall_torsion_bridged_local"]["source_kind"] == "repo_local_bridged"
    assert rows_by_id["offset_core_megatall_torsion_bridged_local"]["evidence_class"] == "repo_local_bridged_graph"
    assert rows_by_id["offset_core_megatall_torsion_bridged_local"]["metadata"]["bridge_report_path"].endswith("bridge_report.json")
    assert rows_by_id["tpu_interference_highrise_local"]["source_kind"] == "repo_local_proxy"

    native_rows = triage["native_roundtrip_candidates"]
    assert any(row["source_id"] == "gtc_public_bridge_bearing_c04_local" for row in native_rows)
    assert triage["summary"]["native_roundtrip_candidate_count"] >= 6
    assert triage["summary"]["solver_benchmark_candidate_count"] >= 8
    assert triage["summary"]["ai_learning_candidate_count"] >= 12
    solver_rows = {row["source_id"] for row in triage["solver_benchmark_candidates"]}
    assert "transfer_podium_tower_proxy_local" in solver_rows
    assert "soft_story_podium_tower_proxy_local" in solver_rows


def test_generator_cli_writes_catalog_and_triage_from_custom_seed(tmp_path: Path) -> None:
    priority_path = tmp_path / "priority.json"
    seed_path = tmp_path / "seed.json"
    out_catalog = tmp_path / "catalog.json"
    out_triage = tmp_path / "triage.json"

    _write_json(
        priority_path,
        {
            "schema_version": "1.0",
            "families": [
                {
                    "id": "transfer_podium_tower",
                    "priority": 1,
                    "why_it_matters": "Transfer podium test.",
                    "irregularity_tags": ["transfer_story", "vertical_irregularity"],
                    "likely_formats": ["mgt", "json"],
                    "authority_fit": "high",
                    "ai_learning_fit": "very-high",
                    "recommended_kpi_or_validation_angle": "transfer demand",
                },
                {
                    "id": "curved_plan_bridge_torsion",
                    "priority": 2,
                    "why_it_matters": "Curved bridge torsion test.",
                    "irregularity_tags": ["curved_plan", "torsion"],
                    "likely_formats": ["mgt", "mcb"],
                    "authority_fit": "high",
                    "ai_learning_fit": "high",
                    "recommended_kpi_or_validation_angle": "torsion ratio",
                },
            ],
        },
    )
    _write_json(
        seed_path,
        {
            "source_records": [
                {
                    "source_id": "alpha_transfer_local",
                    "title": "Alpha transfer local",
                    "family_id": "transfer_podium_tower",
                    "source_kind": "repo_local_source",
                    "formats": ["json_graph"],
                    "local_path": "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/model.json",
                    "source_urls": ["https://example.com/alpha"],
                    "authority_fit": "medium-high",
                    "ai_learning_fit": "very-high",
                    "evidence_class": "repo_local_bridged_graph",
                    "notes": "Local graph source.",
                },
                {
                    "source_id": "beta_bridge_remote",
                    "title": "Beta bridge remote",
                    "family_id": "curved_plan_bridge_torsion",
                    "source_kind": "official_remote_candidate",
                    "formats": ["mgt"],
                    "source_urls": ["https://example.com/beta"],
                    "authority_fit": "high",
                    "ai_learning_fit": "high",
                    "evidence_class": "official_benchmark_remote",
                    "notes": "Remote bridge source.",
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--priority-json",
            str(priority_path),
            "--seed-sources",
            str(seed_path),
            "--out",
            str(out_catalog),
            "--triage-out",
            str(out_triage),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert f"Wrote irregular structure source catalog: {out_catalog}" in proc.stdout
    assert f"Wrote irregular structure triage report: {out_triage}" in proc.stdout

    catalog = json.loads(out_catalog.read_text(encoding="utf-8"))
    triage = json.loads(out_triage.read_text(encoding="utf-8"))

    assert catalog["summary"] == {
        "family_count": 2,
        "source_record_count": 2,
        "local_ready_count": 1,
        "remote_candidate_count": 1,
        "authority_high_like_count": 2,
        "ai_high_like_count": 2,
    }
    assert [row["source_id"] for row in catalog["source_records"]] == [
        "alpha_transfer_local",
        "beta_bridge_remote",
    ]
    assert triage["summary"]["quick_start_local_source_count"] == 1
    assert triage["native_roundtrip_candidates"][0]["source_id"] == "beta_bridge_remote"


def test_build_catalog_rejects_unknown_family_in_source_seed() -> None:
    with pytest.raises(ValueError, match="unknown family id"):
        build_catalog(
            DEFAULT_PRIORITY_PATH,
            source_rows=[
                {
                    "source_id": "bad_source",
                    "title": "Bad source",
                    "family_id": "missing_family",
                    "source_kind": "official_remote_candidate",
                    "formats": ["mgt"],
                    "source_urls": ["https://example.com/bad"],
                    "authority_fit": "high",
                    "ai_learning_fit": "high",
                    "evidence_class": "official_benchmark_remote",
                    "notes": "Broken family reference.",
                }
            ],
        )
