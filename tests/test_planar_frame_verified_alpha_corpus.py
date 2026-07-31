from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = (
    ROOT / "verification" / "planar_frame_verified_alpha_v1" / "corpus.manifest.json"
)


def test_p1_corpus_has_exact_declared_sizes_and_checksum_ready_fixtures() -> None:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert payload["profile"] == "planar_frame_verified_alpha.v1"
    assert payload["status"] == "fixture_manifests_only"
    assert payload["release_eligible"] is False
    expected = {
        "M1": ("medium", 35, 54),
        "M2": ("medium", 36, 56),
        "M3": ("medium", 36, 55),
        "M4": ("medium", 48, 78),
        "M5": ("medium", 55, 90),
        "L1": ("large", 85, 144),
        "L2": ("large", 126, 220),
    }
    assert {row["case_id"] for row in payload["cases"]} == set(expected)
    for row in payload["cases"]:
        assert (row["size"], row["node_count"], row["member_count"]) == expected[
            row["case_id"]
        ]
        fixture_path = ROOT / row["fixture_manifest_path"]
        fixture_bytes = fixture_path.read_bytes()
        assert (
            "sha256:" + hashlib.sha256(fixture_bytes).hexdigest()
            == row["fixture_manifest_sha256"]
        )
        fixture = json.loads(fixture_bytes)
        assert fixture["case_id"] == row["case_id"]
        assert fixture["expected"]["node_count"] == row["node_count"]
        assert fixture["expected"]["member_count"] == row["member_count"]
        assert fixture["claim"] == "fixture_definition_only"
