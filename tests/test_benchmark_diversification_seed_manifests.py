from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("implementation/phase1/open_data")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wind_tpu_hffb_seed_manifest_has_two_diverse_cases() -> None:
    manifest = _load(ROOT / "wind" / "tpu_hffb_seed_manifest.json")
    assert manifest["manifest_family"] == "wind_hffb_seed_selection"
    assert manifest["target_gap"] == "raw_wind_tunnel_hffb_mapping_verification"
    seed_cases = manifest["seed_cases"]
    assert len(seed_cases) == 2
    roles = {row["case_role"] for row in seed_cases}
    assert roles == {"baseline_isolated_highrise", "neighbor_interference_highrise"}
    splits = {row["holdout_split"] for row in seed_cases}
    assert splits == {"val", "holdout"}


def test_peer_spd_column_seed_manifest_covers_train_val_holdout() -> None:
    manifest = _load(ROOT / "pbd_hinge" / "peer_spd_column_seed_manifest.json")
    assert manifest["manifest_family"] == "pbd_hinge_seed_selection"
    assert manifest["target_gap"] == "pbd_dynamic_hinge_refresh_validation"
    seed_cases = manifest["seed_cases"]
    assert len(seed_cases) == 5
    splits = [row["holdout_split"] for row in seed_cases]
    assert splits.count("train") == 2
    assert splits.count("val") == 2
    assert splits.count("holdout") == 1
    assert any("rebar-sensitive" in row["why"] or "rebar-sensitive" in row["why"].lower() for row in seed_cases)
