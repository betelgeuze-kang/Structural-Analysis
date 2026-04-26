from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def test_prepare_rhino_3dm_baseline_bridge(tmp_path: Path) -> None:
    vendor_dir = Path("implementation/phase1/_vendor").resolve()
    sys.path.insert(0, str(vendor_dir))
    import rhino3dm  # type: ignore

    model = rhino3dm.File3dm()
    attrs = rhino3dm.ObjectAttributes()
    curve_a = rhino3dm.PolylineCurve(
        [
            rhino3dm.Point3d(0.0, 0.0, 0.0),
            rhino3dm.Point3d(5.0, 0.0, 0.0),
            rhino3dm.Point3d(5.0, 5.0, 0.0),
        ]
    )
    curve_b = rhino3dm.PolylineCurve(
        [
            rhino3dm.Point3d(2.0, 1.0, 0.0),
            rhino3dm.Point3d(2.0, 1.0, 3.0),
        ]
    )
    model.Objects.AddCurve(curve_a, attrs)
    model.Objects.AddCurve(curve_b, attrs)
    rhino_path = tmp_path / "sample.3dm"
    model.Write(str(rhino_path), 6)

    out_dir = tmp_path / "out"
    model_json = out_dir / "model.json"
    dataset_npz = out_dir / "dataset.npz"
    report = out_dir / "bridge_report.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/prepare_rhino_3dm_baseline_bridge.py",
            "--source-id",
            "sample_source",
            "--rhino-3dm",
            str(rhino_path),
            "--model-json-out",
            str(model_json),
            "--npz-out",
            str(dataset_npz),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert report_payload["contract_pass"] is True
    assert report_payload["reason_code"] == "PASS"
    assert report_payload["summary"]["viewer_ready"] is True
    assert report_payload["summary"]["element_count"] == 3
    assert report_payload["summary"]["accepted_object_count"] == 2

    model_payload = json.loads(model_json.read_text(encoding="utf-8"))
    assert model_payload["topology_metrics"]["element_count"] == 3
    assert len(model_payload["model"]["nodes"]) >= 4
    assert model_payload["model"]["elements"][0]["family"] == "beam"

    dataset = np.load(dataset_npz, allow_pickle=True)
    assert "member_ids" in dataset.files
    assert "story_band_index" in dataset.files
    assert dataset["member_ids"].shape[0] == 3
    assert dataset["story_band_index"].shape[0] == 3
