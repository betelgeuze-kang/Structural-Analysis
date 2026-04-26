from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_template(path: Path, case_id: str, case_label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "case": {
            "case_id": case_id,
            "case_label": case_label,
        },
        "attestation": {
            "reviewer_name": "PENDING_REAL_REVIEWER_NAME_FILL_CASE_ATTESTATION_MANIFEST",
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_generate_case_onepage_attestation_manifests_prefers_unique_real_cases(tmp_path: Path) -> None:
    kickoff_dir = tmp_path / "kickoff"
    template_dir = kickoff_dir / "case_onepage_attestation_templates"
    report_path = kickoff_dir / "attestation_manifest_generation_report.json"

    _write_template(
        template_dir / "00.sample_case.authority_onepage.reviewer_attestation.template.json",
        "sample_case",
        "Sample Case",
    )
    _write_template(
        template_dir / "00.peer_tbi_tall_building_ndtha.authority_onepage.reviewer_attestation.template.json",
        "peer_tbi_tall_building_ndtha",
        "Peer 00",
    )
    _write_template(
        template_dir / "01.peer_tbi_tall_building_ndtha.authority_onepage.reviewer_attestation.template.json",
        "peer_tbi_tall_building_ndtha",
        "Peer 01",
    )
    _write_template(
        template_dir / "02.nheri_designsafe_ssi.authority_onepage.reviewer_attestation.template.json",
        "nheri_designsafe_ssi",
        "NHERI SSI",
    )

    script = Path("implementation/phase1/generate_case_onepage_attestation_manifests.py")
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--kickoff-dir",
            str(kickoff_dir),
            "--reviewer-name",
            "Friend Demo Reviewer",
            "--reviewer-role",
            "informal external reviewer",
            "--reviewer-license-id",
            "demo-review-no-license",
            "--authority-name",
            "informal demo receipt authority",
            "--report-out",
            str(report_path),
        ],
        check=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["template_count"] == 2
    assert report["summary"]["manifest_count"] == 2
    case_ids = [row["case_id"] for row in report["rows"]]
    assert case_ids == ["nheri_designsafe_ssi", "peer_tbi_tall_building_ndtha"]

    manifest_paths = [Path(row["manifest_json"]) for row in report["rows"]]
    assert all(path.exists() for path in manifest_paths)
    peer_manifest = json.loads(manifest_paths[1].read_text(encoding="utf-8"))
    assert peer_manifest["case"]["case_label"] == "Peer 01"
    assert peer_manifest["attestation"]["reviewer_name"] == "Friend Demo Reviewer"
