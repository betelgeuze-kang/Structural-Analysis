from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def test_prepare_opensees_shell_beam_mix_baseline_bridge(tmp_path: Path) -> None:
    model_path = tmp_path / "shell_beam_mix.tcl"
    model_json_out = tmp_path / "bridge" / "model.json"
    dataset_npz_out = tmp_path / "bridge" / "dataset.npz"
    report_out = tmp_path / "bridge" / "bridge_report.json"

    model_path.write_text(
        "\n".join(
            [
                "node 1 0.0 0.0 0.0",
                "node 2 8.0 0.0 0.0",
                "node 3 8.0 8.0 0.0",
                "node 4 0.0 8.0 0.0",
                "node 5 0.0 0.0 4.0",
                "node 6 8.0 0.0 4.0",
                "node 7 8.0 8.0 4.0",
                "node 8 0.0 8.0 4.0",
                "element ShellMITC4 10 1 2 3 4 1",
                "element elasticBeamColumn 11 1 5 1 1 1",
                "element elasticBeamColumn 12 5 6 1 1 1",
                "element corotTruss 13 2 7 1 1",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_opensees_shell_beam_mix_baseline_bridge.py",
            "--source-id",
            "SCBF16B_shell_beam_mix",
            "--opensees-model",
            str(model_path),
            "--model-json-out",
            str(model_json_out),
            "--npz-out",
            str(dataset_npz_out),
            "--report-out",
            str(report_out),
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["viewer_ready"] is True
    assert report["summary"]["element_count"] == 4
    assert "ShellMITC4=1" in report["summary"]["accepted_type_label"]

    model_payload = json.loads(model_json_out.read_text(encoding="utf-8"))
    assert model_payload["model_kind"] == "opensees_text_baseline"
    assert len(model_payload["model"]["nodes"]) == 8
    assert len(model_payload["model"]["elements"]) == 4
    families = {row["family"] for row in model_payload["model"]["elements"]}
    assert "slab" in families
    assert "column" in families
    assert "beam" in families or "beam_brace" in families

    dataset = np.load(dataset_npz_out, allow_pickle=True)
    assert "member_ids" in dataset.files
    assert "story_band_index" in dataset.files
    assert dataset["member_ids"].shape[0] == 4
    assert dataset["group_index_per_member"].shape[0] == 4
    assert report["summary"]["source_profile_label"] == "shell-beam mix"
