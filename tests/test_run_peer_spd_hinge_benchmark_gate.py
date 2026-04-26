from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_peer_spd_hinge_benchmark_gate_passes() -> None:
    registry = Path('implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json')
    out = Path('/tmp/peer_spd_hinge_benchmark_gate.test.json')
    proc = subprocess.run(
        [
            sys.executable,
            'implementation/phase1/run_peer_spd_hinge_benchmark_gate.py',
            '--asset-registry',
            str(registry),
            '--out',
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out)
    assert report['contract_pass'] is True
    assert report['observed']['train_count'] >= 2
    assert report['observed']['val_count'] >= 2
    assert report['observed']['holdout_count'] >= 1
