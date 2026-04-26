from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_edefense_peer_blind_prediction_source_manifest as manifest_builder  # noqa: E402


def test_peer_public_bundle_closes_geometry_material_excitation_only(tmp_path: Path) -> None:
    root = tmp_path / "peer_bundle"
    root.mkdir()
    (root / "Materials.zip").write_bytes(b"zip")
    (root / "GMs.xlsx").write_bytes(b"xlsx")
    (root / "Construction_Drawings.pdf").write_bytes(b"pdf")

    payload = manifest_builder.build_manifest(root)

    assert payload["expected_groups"]["geometry_model"]["present"] is True
    assert payload["expected_groups"]["material_properties"]["present"] is True
    assert payload["expected_groups"]["excitation_history"]["present"] is True
    assert payload["expected_groups"]["measured_response"]["present"] is False
    assert payload["contract_pass"] is False
