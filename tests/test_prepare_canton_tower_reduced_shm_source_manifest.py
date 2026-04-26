from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_canton_tower_reduced_shm_source_manifest as canton_manifest  # noqa: E402


def test_canton_tower_manifest_detects_required_groups(tmp_path: Path) -> None:
    root = tmp_path / "canton"
    root.mkdir()
    (root / "system_matrices.mat").write_bytes(b"matrices")
    (root / "Phase_I_FE_model_description.pdf").write_bytes(b"pdf")
    (root / "data_all.zip").write_bytes(b"zip")

    payload = canton_manifest.build_manifest(root)

    assert payload["contract_pass"] is True
    assert payload["expected_groups"]["system_matrices"]["present"] is True
    assert payload["expected_groups"]["benchmark_docs"]["present"] is True
    assert payload["expected_groups"]["measured_response"]["present"] is True
    assert payload["summary"]["file_count"] == 3


def test_canton_tower_manifest_reports_missing_groups(tmp_path: Path) -> None:
    root = tmp_path / "canton"
    root.mkdir()
    (root / "system_matrices.mat").write_bytes(b"matrices")

    payload = canton_manifest.build_manifest(root)

    assert payload["contract_pass"] is False
    assert payload["expected_groups"]["system_matrices"]["present"] is True
    assert payload["expected_groups"]["benchmark_docs"]["present"] is False
    assert payload["expected_groups"]["measured_response"]["present"] is False
