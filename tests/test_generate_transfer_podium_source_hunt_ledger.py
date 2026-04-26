import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generate_transfer_podium_source_hunt_ledger_outputs_expected_fields(tmp_path):
    script = REPO_ROOT / "implementation/phase1/generate_transfer_podium_source_hunt_ledger.py"
    subprocess.run(["python3", str(script)], check=True, cwd=REPO_ROOT)

    payload_path = REPO_ROOT / "implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.json"
    assert payload_path.exists()

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["family_id"] == "transfer_podium_tower"
    assert payload["canonical_status"] == "not_promoted"
    assert "official PEER docs checked, native package not found as of" in payload["audit_statement"]
    assert payload["search_sequence"] == [
        "author_personal_page",
        "lab_site",
        "github_raw",
        "supplemental_zip",
    ]
    assert any("GitHub code search" in finding for finding in payload["search_findings"])
    assert any(
        topic["title"] == "Backstay Effect"
        for topic in payload["task12_transfer_focus_topics"]
    )
    assert any(
        candidate["title"] == "Core-wall tower with podium having separate foundation system"
        for candidate in payload["task12_publication_title_candidates"]
    )
    assert any(
        pattern["pattern_id"] == "backstay_transfer_model"
        for pattern in payload["supplemental_zip_hunt_patterns"]
    )
    assert any(
        pattern["pattern_id"] == "task12_transfer_appendix"
        for pattern in payload["reference_pdf_recursive_hunt_patterns"]
    )
    author_names = [row["name"] for row in payload["authors"]]
    assert "John Wallace" in author_names
    assert "Tony Yang" in author_names
    john = next(row for row in payload["authors"] if row["name"] == "John Wallace")
    assert any("peer_center.htm" in url for url in john["checked_subtargets"])
    assert john["preferred_topic_match_order"][0] == "core_wall_tower_with_podium"
    assert john["publication_cv_candidates"][0]["follow_pdf_recursively"] is True
    assert ".zip" in john["publication_cv_candidates"][0]["whitelist_suffixes"]
    tony = next(row for row in payload["authors"] if row["name"] == "Tony Yang")
    assert any(
        "opensees-navigator" in row["url"]
        for row in tony["publication_cv_candidates"]
    )
