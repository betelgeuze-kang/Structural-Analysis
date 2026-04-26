from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_irregular_top5_execution_manifest_prefers_local_ready_sources(tmp_path: Path) -> None:
    source_catalog = tmp_path / "catalog.json"
    priority = tmp_path / "priority.json"
    triage = tmp_path / "triage.json"
    collection = tmp_path / "collection.json"
    out = tmp_path / "top5.json"

    families = []
    records = []
    priority_rows = []
    for idx in range(1, 7):
        family_id = f"family_{idx}"
        priority_rows.append({
            "id": family_id,
            "priority": idx,
            "authority_fit": "high",
            "ai_learning_fit": "very-high",
            "recommended_kpi_or_validation_angle": f"kpi-{idx}",
            "irregularity_tags": [f"tag-{idx}"],
            "why_it_matters": f"why-{idx}",
        })
        families.append({
            "id": family_id,
            "priority": idx,
            "authority_fit": "high",
            "ai_learning_fit": "very-high",
            "recommended_kpi_or_validation_angle": f"kpi-{idx}",
            "irregularity_tags": [f"tag-{idx}"],
            "why_it_matters": f"why-{idx}",
            "source_record_count": 1,
            "local_ready_source_count": 1 if idx % 2 == 1 else 0,
        })
        records.append({
            "source_id": f"source_{idx}",
            "family_id": family_id,
            "priority": idx,
            "title": f"Source {idx}",
            "source_kind": "repo_local_source" if idx % 2 == 1 else "official_remote_candidate",
            "primary_format": "mgt",
            "source_urls": [f"https://example.com/{idx}.mgt"],
            "local_path": f"/tmp/case_{idx}.mgt" if idx % 2 == 1 else "",
            "collection_status": "local_ready" if idx % 2 == 1 else "remote_candidate",
        })

    _write(source_catalog, {"track_name": "irregular", "summary": {"family_count": 20, "source_record_count": 22}, "structure_families": families, "source_records": records})
    _write(priority, {"families": priority_rows})
    _write(triage, {"summary": {"native_roundtrip_candidate_count": 14, "solver_benchmark_candidate_count": 11, "ai_learning_candidate_count": 22, "quick_start_local_source_count": 7}})
    _write(collection, {"summary": {"collected_count": 7, "metadata_only_remote_candidate_count": 15}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_irregular_top5_execution_manifest.py",
            "--source-catalog", str(source_catalog),
            "--priority-families", str(priority),
            "--triage-report", str(triage),
            "--collection-report", str(collection),
            "--out", str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["top5_count"] == 5
    assert report["summary"]["top5_local_ready_count"] == 3
    assert report["summary"]["top5_reference_collected_count"] == 0
    assert report["summary"]["top5_remote_needed_count"] == 2
    assert report["top5_families"][0]["family_id"] == "family_1"
    assert report["top5_families"][0]["execution_mode"] == "ready_local_canonical_now"
    assert report["top5_families"][1]["execution_mode"] == "remote_source_hunt_needed"
    assert "top5=5" in report["summary_line"]
    assert report["summary"]["top5_canonical_ready_count"] == 3


def test_generate_irregular_top5_execution_manifest_marks_proxy_ready_sources(tmp_path: Path) -> None:
    source_catalog = tmp_path / "catalog.json"
    priority = tmp_path / "priority.json"
    triage = tmp_path / "triage.json"
    collection = tmp_path / "collection.json"
    out = tmp_path / "top5.json"
    local_model = tmp_path / "proxy_model.json"
    local_model.write_text("{}\n", encoding="utf-8")

    families = []
    records = []
    priority_rows = []
    for idx in range(1, 6):
        family_id = f"family_{idx}"
        priority_rows.append(
            {
                "id": family_id,
                "priority": idx,
                "authority_fit": "high",
                "ai_learning_fit": "very-high",
                "recommended_kpi_or_validation_angle": f"kpi-{idx}",
                "irregularity_tags": [f"tag-{idx}"],
                "why_it_matters": f"why-{idx}",
            }
        )
        families.append(
            {
                "id": family_id,
                "priority": idx,
                "authority_fit": "high",
                "ai_learning_fit": "very-high",
                "recommended_kpi_or_validation_angle": f"kpi-{idx}",
                "irregularity_tags": [f"tag-{idx}"],
                "why_it_matters": f"why-{idx}",
                "source_record_count": 1,
                "local_ready_source_count": 1,
            }
        )
        records.append(
            {
                "source_id": f"proxy_source_{idx}",
                "family_id": family_id,
                "priority": idx,
                "title": f"Proxy source {idx}",
                "source_kind": "repo_local_proxy",
                "primary_format": "json_graph",
                "source_urls": [f"https://example.com/proxy-{idx}.json"],
                "local_path": str(local_model),
                "collection_status": "local_ready",
            }
        )

    _write(
        source_catalog,
        {
            "track_name": "irregular",
            "summary": {"family_count": 5, "source_record_count": 5},
            "structure_families": families,
            "source_records": records,
        },
    )
    _write(priority, {"families": priority_rows})
    _write(
        triage,
        {
            "summary": {
                "native_roundtrip_candidate_count": 5,
                "solver_benchmark_candidate_count": 5,
                "ai_learning_candidate_count": 5,
                "quick_start_local_source_count": 5,
            }
        },
    )
    _write(collection, {"summary": {"collected_count": 5, "metadata_only_remote_candidate_count": 0}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_irregular_top5_execution_manifest.py",
            "--source-catalog", str(source_catalog),
            "--priority-families", str(priority),
            "--triage-report", str(triage),
            "--collection-report", str(collection),
            "--out", str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["top5_families"][0]["execution_mode"] == "ready_local_proxy_now"
    assert report["summary"]["top5_proxy_ready_count"] == 5
    assert report["summary"]["top5_bridged_ready_count"] == 0
    assert report["summary"]["top5_canonical_ready_count"] == 0


def test_generate_irregular_top5_execution_manifest_distinguishes_bridged_and_canonical_sources(tmp_path: Path) -> None:
    source_catalog = tmp_path / "catalog.json"
    priority = tmp_path / "priority.json"
    triage = tmp_path / "triage.json"
    collection = tmp_path / "collection.json"
    out = tmp_path / "top5.json"
    local_model = tmp_path / "model.json"
    local_model.write_text("{}\n", encoding="utf-8")
    local_mgt = tmp_path / "case.mgt"
    local_mgt.write_text("*UNIT\n", encoding="utf-8")

    families = []
    records = []
    priority_rows = []
    source_rows = [
        ("family_1", "repo_local_bridged", "repo_local_bridged_graph", str(local_model)),
        ("family_2", "public_native_source", "public_native_mgt", str(local_mgt)),
    ]
    for idx, (family_id, source_kind, evidence_class, local_path) in enumerate(source_rows, start=1):
        priority_rows.append(
            {
                "id": family_id,
                "priority": idx,
                "authority_fit": "high",
                "ai_learning_fit": "very-high",
                "recommended_kpi_or_validation_angle": f"kpi-{idx}",
                "irregularity_tags": [f"tag-{idx}"],
                "why_it_matters": f"why-{idx}",
            }
        )
        families.append(
            {
                "id": family_id,
                "priority": idx,
                "authority_fit": "high",
                "ai_learning_fit": "very-high",
                "recommended_kpi_or_validation_angle": f"kpi-{idx}",
                "irregularity_tags": [f"tag-{idx}"],
                "why_it_matters": f"why-{idx}",
                "source_record_count": 1,
                "local_ready_source_count": 1,
            }
        )
        records.append(
            {
                "source_id": f"source_{idx}",
                "family_id": family_id,
                "priority": idx,
                "title": f"Source {idx}",
                "source_kind": source_kind,
                "evidence_class": evidence_class,
                "primary_format": "json_graph" if local_path.endswith(".json") else "mgt",
                "source_urls": [f"https://example.com/{idx}"],
                "local_path": local_path,
                "collection_status": "local_ready",
            }
        )

    _write(source_catalog, {"track_name": "irregular", "summary": {"family_count": 2, "source_record_count": 2}, "structure_families": families, "source_records": records})
    _write(priority, {"families": priority_rows})
    _write(triage, {"summary": {"native_roundtrip_candidate_count": 2, "solver_benchmark_candidate_count": 2, "ai_learning_candidate_count": 2, "quick_start_local_source_count": 2}})
    _write(collection, {"summary": {"collected_count": 2, "metadata_only_remote_candidate_count": 0}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_irregular_top5_execution_manifest.py",
            "--source-catalog", str(source_catalog),
            "--priority-families", str(priority),
            "--triage-report", str(triage),
            "--collection-report", str(collection),
            "--out", str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    modes = {row["family_id"]: row["execution_mode"] for row in report["top5_families"]}
    assert modes["family_1"] == "ready_local_bridged_now"
    assert modes["family_2"] == "ready_local_canonical_now"
    assert report["summary"]["top5_bridged_ready_count"] == 1
    assert report["summary"]["top5_canonical_ready_count"] == 1


def test_generate_irregular_top5_execution_manifest_promotes_bridge_report_backed_proxy_rows(tmp_path: Path) -> None:
    source_catalog = tmp_path / "catalog.json"
    priority = tmp_path / "priority.json"
    triage = tmp_path / "triage.json"
    collection = tmp_path / "collection.json"
    out = tmp_path / "top5.json"
    bridged_dir = tmp_path / "bridged" / "case"
    bridged_dir.mkdir(parents=True)
    local_model = bridged_dir / "model.json"
    bridge_report = bridged_dir / "bridge_report.json"
    local_model.write_text("{}\n", encoding="utf-8")
    bridge_report.write_text("{\"contract_pass\": true}\n", encoding="utf-8")

    _write(
        source_catalog,
        {
            "track_name": "irregular",
            "summary": {"family_count": 1, "source_record_count": 1},
            "structure_families": [
                {
                    "id": "family_1",
                    "priority": 1,
                    "authority_fit": "high",
                    "ai_learning_fit": "very-high",
                    "recommended_kpi_or_validation_angle": "kpi-1",
                    "irregularity_tags": ["tag-1"],
                    "why_it_matters": "why-1",
                    "source_record_count": 1,
                    "local_ready_source_count": 1,
                }
            ],
            "source_records": [
                {
                    "source_id": "source_1",
                    "family_id": "family_1",
                    "priority": 1,
                    "title": "Source 1",
                    "source_kind": "repo_local_proxy",
                    "evidence_class": "repo_local_proxy",
                    "primary_format": "json_graph",
                    "source_urls": ["https://example.com/1"],
                    "local_path": str(local_model),
                    "companion_paths": [str(bridge_report)],
                    "collection_status": "local_ready",
                }
            ],
        },
    )
    _write(
        priority,
        {
            "families": [
                {
                    "id": "family_1",
                    "priority": 1,
                    "authority_fit": "high",
                    "ai_learning_fit": "very-high",
                    "recommended_kpi_or_validation_angle": "kpi-1",
                    "irregularity_tags": ["tag-1"],
                    "why_it_matters": "why-1",
                }
            ]
        },
    )
    _write(
        triage,
        {
            "summary": {
                "native_roundtrip_candidate_count": 0,
                "solver_benchmark_candidate_count": 1,
                "ai_learning_candidate_count": 1,
                "quick_start_local_source_count": 1,
            }
        },
    )
    _write(collection, {"summary": {"collected_count": 1, "metadata_only_remote_candidate_count": 0}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_irregular_top5_execution_manifest.py",
            "--source-catalog", str(source_catalog),
            "--priority-families", str(priority),
            "--triage-report", str(triage),
            "--collection-report", str(collection),
            "--out", str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["top5_families"][0]["execution_mode"] == "ready_local_bridged_now"
    assert report["summary"]["top5_bridged_ready_count"] == 1
    assert report["summary"]["top5_proxy_ready_count"] == 0
