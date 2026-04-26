from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_peer_spd_column_seed_candidates_matches_all_seeds(tmp_path: Path) -> None:
    rectangular = tmp_path / "rectangular.txt"
    rectangular.write_text(
        "\t".join(
            [
                "No.",
                "Specimen Name",
                "f'c (MPa)",
                "Axial Load (kN)",
                "B (mm)",
                "H (mm)",
                "Reinf Ratio",
                "Type of confinement",
                "Vol Trans Reinf Ratio",
            ]
        )
        + "\n"
        + "\t".join(["101", "Family A, Col 1", "30", "400", "400", "400", "0.020", "RO: ties", "0.010"])
        + "\n"
        + "\t".join(["102", "Family B, Col 2", "30", "1500", "400", "400", "0.024", "RI: ties", "0.012"])
        + "\n"
        + "\t".join(["103", "Family C, Col 3", "30", "500", "400", "400", "0.040", "RI: ties", "0.020"])
        + "\n",
        encoding="utf-8",
    )
    spiral = tmp_path / "spiral.txt"
    spiral.write_text(
        "\t".join(
            [
                "No.",
                "Specimen Name",
                "Diameter",
                "f'c",
                "P",
                "rho Long",
                "rho Spiral",
                "Configuration",
            ]
        )
        + "\n"
        + "\t".join(["201", "Family S, Col 1", "500", "30", "1500", "0.020", "0.500", "spiral"])
        + "\n"
        + "\t".join(["202", "Family H, Col 2", "500", "30", "2200", "0.018", "0.450", "spiral"])
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "candidates.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_peer_spd_column_seed_candidates.py",
            "--seed-manifest",
            "implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json",
            "--rectangular-table",
            str(rectangular),
            "--spiral-table",
            str(spiral),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out)
    assert report["contract_pass"] is True
    assert report["summary"]["matched_seed_count"] == 5
    by_seed = {row["seed_id"]: row for row in report["rows"]}
    assert by_seed["peer_spd_rc_column_rectangular_seed_01"]["selected_candidate"]["specimen_id"] == "103"
    assert by_seed["peer_spd_rc_column_rectangular_seed_02"]["selected_candidate"]["specimen_id"] == "102"
    assert by_seed["peer_spd_rc_column_spiral_seed_01"]["selected_candidate"]["specimen_id"] in {"201", "202"}
    assert by_seed["peer_spd_rc_column_rebar_sensitive_seed_01"]["selected_candidate"]["specimen_id"] == "103"
    assert by_seed["peer_spd_rc_column_holdout_seed_01"]["candidate_count"] >= 1
