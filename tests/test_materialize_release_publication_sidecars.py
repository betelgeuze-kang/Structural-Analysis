from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/materialize_release_publication_sidecars.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_materialize_release_publication_sidecars_recreates_manifest_assets(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    hardest = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    workflow = tmp_path / "workflow_productization_gate_report.json"
    midas = release_dir / "midas_native_roundtrip" / "midas_native_writeback_diff_receipts_report.json"
    out = release_dir / "release_publication_sidecar_materialization_report.json"

    _write_json(
        hardest,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "cases": [
                {
                    "case_id": "peer_tbi_tall_building_ndtha",
                    "label": "PEER TBI Tall Building NDTHA",
                    "ready_to_start": True,
                },
                {
                    "case_id": "nheri_designsafe_ssi",
                    "label": "NHERI DesignSafe SSI",
                    "ready_to_start": True,
                },
            ],
        },
    )
    _write_json(
        workflow,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "case_onepage_attestation_case_count": 2,
                "case_onepage_attestation_manifest_count": 2,
                "case_onepage_attestation_template_count": 0,
                "case_onepage_attestation_receipt_count": 2,
                "case_onepage_attestation_attested_count": 2,
                "case_onepage_attestation_source_label": "manifest=2",
                "case_onepage_attestation_status_label": "MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED=2",
            },
        },
    )
    _write_json(
        midas,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "exact_topology_structural_preview_candidate_total": 8,
                "exact_topology_structural_preview_pending_candidate_count": 0,
                "exact_topology_structural_preview_public_archive_promoted_candidate_count": 3,
                "exact_topology_structural_preview_korean_candidate_total": 5,
                "exact_topology_structural_preview_korean_pending_candidate_count": 0,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--release-dir",
            str(release_dir),
            "--hardest-external-10case-report",
            str(hardest),
            "--workflow-productization-report",
            str(workflow),
            "--midas-native-writeback-report",
            str(midas),
            "--out",
            str(out),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True

    case_index = release_dir / "external_benchmark_kickoff" / "case_onepage_attestation_index.json"
    case_markdown = case_index.with_suffix(".md")
    queue = release_dir / "midas_native_roundtrip" / "exact_topology_structural_preview_promotion_queue.json"
    queue_markdown = queue.with_suffix(".md")

    assert case_index.exists()
    assert case_markdown.exists()
    assert queue.exists()
    assert queue_markdown.exists()

    case_payload = json.loads(case_index.read_text(encoding="utf-8"))
    assert case_payload["summary"]["status_label"] == "MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED=2"
    assert len(case_payload["cases"]) == 2
    assert "PEER TBI Tall Building NDTHA" in case_markdown.read_text(encoding="utf-8")

    queue_payload = json.loads(queue.read_text(encoding="utf-8"))
    assert queue_payload["summary"]["candidate_total"] == 8
    assert queue_payload["summary"]["pending_candidate_count"] == 0
    assert queue_payload["summary"]["state"] == "closed_until_new_public_archive_exact_topology_candidate"
    assert "No pending exact-topology" in queue_markdown.read_text(encoding="utf-8")
