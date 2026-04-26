from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/parse_opensees_to_csr.py")


def test_parse_opensees_to_csr_passes_on_simple_model(tmp_path: Path) -> None:
    model = tmp_path / "simple_frame.tcl"
    model.write_text(
        "\n".join(
            [
                "model BasicBuilder -ndm 3 -ndf 6",
                "node 1 0.0 0.0 0.0",
                "node 2 1.0 0.0 0.0",
                "node 3 1.0 1.0 0.0",
                "node 4 0.0 1.0 0.0",
                "node 5 0.0 0.0 1.0",
                "node 6 1.0 0.0 1.0",
                "node 7 1.0 1.0 1.0",
                "node 8 0.0 1.0 1.0",
                "element elasticBeamColumn 11 1 2 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 12 2 3 1.0 2.0e11 1.0e-4 1",
                "element truss 13 3 4 1.0 1",
                "element truss 14 4 1 1.0 1",
                "element truss 15 5 6 1.0 1",
                "element truss 16 6 7 1.0 1",
                "element truss 17 7 8 1.0 1",
                "element truss 18 8 5 1.0 1",
                "element elasticBeamColumn 19 1 5 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 20 3 7 1.0 2.0e11 1.0e-4 1",
                "equalDOF 1 3 1 2 3",
            ]
        ),
        encoding="utf-8",
    )

    edges_out = tmp_path / "edges.json"
    csr_out = tmp_path / "csr.npz"
    report_out = tmp_path / "report.json"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--model",
        str(model),
        "--edges-out",
        str(edges_out),
        "--csr-out",
        str(csr_out),
        "--report-out",
        str(report_out),
        "--require-real-topology",
        "--forbid-synthetic-source",
        "--no-require-shell-beam-mix",
        "--min-nodes",
        "8",
        "--min-edge-node-ratio",
        "0.5",
        "--min-degree-entropy",
        "0.0",
        "--min-largest-component-ratio",
        "0.4",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["real_topology_pass"] is True
    assert report["metrics"]["node_count"] >= 8
    assert edges_out.exists()
    assert csr_out.exists()


def test_parse_opensees_to_csr_fails_without_shell_beam_mix_under_strict_mode(tmp_path: Path) -> None:
    model = tmp_path / "beam_only_frame.tcl"
    model.write_text(
        "\n".join(
            [
                "model BasicBuilder -ndm 3 -ndf 6",
                "node 1 0.0 0.0 0.0",
                "node 2 1.0 0.0 0.0",
                "node 3 1.0 1.0 0.0",
                "node 4 0.0 1.0 0.0",
                "node 5 0.0 0.0 1.0",
                "node 6 1.0 0.0 1.0",
                "node 7 1.0 1.0 1.0",
                "node 8 0.0 1.0 1.0",
                "element elasticBeamColumn 11 1 2 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 12 2 3 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 13 3 4 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 14 4 1 1.0 2.0e11 1.0e-4 1",
            ]
        ),
        encoding="utf-8",
    )

    report_out = tmp_path / "report.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--model",
        str(model),
        "--report-out",
        str(report_out),
        "--require-real-topology",
        "--require-shell-beam-mix",
        "--forbid-synthetic-source",
        "--min-nodes",
        "8",
        "--min-edge-node-ratio",
        "0.5",
        "--min-degree-entropy",
        "0.0",
        "--min-largest-component-ratio",
        "0.4",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_SHELL_BEAM_MIX"
    assert report["checks"]["shell_beam_mix_pass"] is False


def test_parse_opensees_synthetic_marker_checks_filename_only(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample_dataset"
    sample_dir.mkdir(parents=True, exist_ok=True)
    model = sample_dir / "real_frame.tcl"
    model.write_text(
        "\n".join(
            [
                "model BasicBuilder -ndm 3 -ndf 6",
                "node 1 0.0 0.0 0.0",
                "node 2 1.0 0.0 0.0",
                "node 3 1.0 1.0 0.0",
                "node 4 0.0 1.0 0.0",
                "node 5 0.0 0.0 1.0",
                "node 6 1.0 0.0 1.0",
                "node 7 1.0 1.0 1.0",
                "node 8 0.0 1.0 1.0",
                "element elasticBeamColumn 11 1 2 1.0 2.0e11 1.0e-4 1",
                "element elasticBeamColumn 12 2 3 1.0 2.0e11 1.0e-4 1",
                "element truss 13 3 4 1.0 1",
                "element truss 14 4 1 1.0 1",
                "element truss 15 5 6 1.0 1",
                "element truss 16 6 7 1.0 1",
                "element truss 17 7 8 1.0 1",
                "element truss 18 8 5 1.0 1",
            ]
        ),
        encoding="utf-8",
    )
    report_out = tmp_path / "report.json"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--model",
        str(model),
        "--report-out",
        str(report_out),
        "--require-real-topology",
        "--forbid-synthetic-source",
        "--no-require-shell-beam-mix",
        "--min-nodes",
        "8",
        "--min-edge-node-ratio",
        "0.5",
        "--min-degree-entropy",
        "0.0",
        "--min-largest-component-ratio",
        "0.4",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["checks"]["synthetic_source_detected"] is False
