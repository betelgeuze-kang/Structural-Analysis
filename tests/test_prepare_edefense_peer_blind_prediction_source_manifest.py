from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_edefense_peer_blind_prediction_source_manifest as edefense_manifest  # noqa: E402


def test_edefense_manifest_detects_required_groups(tmp_path: Path) -> None:
    root = tmp_path / "edefense"
    root.mkdir()
    (root / "frame_geometry.json").write_text("{}", encoding="utf-8")
    (root / "material_properties.csv").write_text("fc,fy\n24,400\n", encoding="utf-8")
    (root / "ground_motion.csv").write_text("t,ax\n0,0.1\n", encoding="utf-8")
    (root / "measured_response.csv").write_text("t,u1\n0,0.0\n", encoding="utf-8")
    (root / "instructions.pdf").write_bytes(b"pdf")

    payload = edefense_manifest.build_manifest(root)

    assert payload["contract_pass"] is True
    assert payload["expected_groups"]["geometry_model"]["present"] is True
    assert payload["expected_groups"]["material_properties"]["present"] is True
    assert payload["expected_groups"]["excitation_history"]["present"] is True
    assert payload["expected_groups"]["measured_response"]["present"] is True
    assert payload["expected_groups"]["reference_docs"]["present"] is True


def test_edefense_manifest_reports_partial_package(tmp_path: Path) -> None:
    root = tmp_path / "edefense"
    root.mkdir()
    (root / "frame_geometry.json").write_text("{}", encoding="utf-8")
    (root / "instructions.pdf").write_bytes(b"pdf")

    payload = edefense_manifest.build_manifest(root)

    assert payload["contract_pass"] is False
    assert payload["expected_groups"]["geometry_model"]["present"] is True
    assert payload["expected_groups"]["material_properties"]["present"] is False
    assert payload["expected_groups"]["excitation_history"]["present"] is False
    assert payload["expected_groups"]["measured_response"]["present"] is False


def test_edefense_manifest_counts_official_workbook_as_measured_response_public_landing(tmp_path: Path) -> None:
    root = tmp_path / "edefense"
    root.mkdir()
    (root / "frame_geometry.json").write_text("{}", encoding="utf-8")
    (root / "material_properties.csv").write_text("fc,fy\n24,400\n", encoding="utf-8")
    (root / "GMs.xlsx").write_bytes(b"xlsx")
    (root / "Experimentalresults.xlsx").write_bytes(b"xlsx")

    payload = edefense_manifest.build_manifest(root)
    measured = payload["expected_groups"]["measured_response"]

    assert payload["contract_pass"] is True
    assert measured["present"] is True
    assert measured["public_landing_present"] is True
    assert measured["public_landing_mode"] == "workbook_only"
    assert measured["workbook_candidate_count"] == 1
    assert measured["csv_like_candidate_count"] == 0
    assert measured["explicit_channel_claims"]["acceleration"] is False
    assert measured["explicit_channel_claims"]["drift"] is False
    assert measured["explicit_channel_claims"]["sensor_manifest"] is False
    assert measured["matched_files"] == ["Experimentalresults.xlsx"]


def test_edefense_manifest_accepts_measured_response_workbook(tmp_path: Path) -> None:
    root = tmp_path / "edefense"
    root.mkdir()
    (root / "frame_geometry.json").write_text("{}", encoding="utf-8")
    (root / "material_properties.csv").write_text("fc,fy\n24,400\n", encoding="utf-8")
    (root / "GMs.xlsx").write_text("placeholder", encoding="utf-8")
    (root / "Experimentalresults.xlsx").write_text("placeholder", encoding="utf-8")

    payload = edefense_manifest.build_manifest(root)

    assert payload["expected_groups"]["measured_response"]["present"] is True
    assert "Experimentalresults.xlsx" in payload["expected_groups"]["measured_response"]["matched_files"]
