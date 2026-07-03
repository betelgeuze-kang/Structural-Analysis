from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_public_benchmark_dude_enrichment_rows.py"
)
PHASE2_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_public_benchmark_phase2_from_rows.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_dude_enrichment_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

phase2_spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_phase2_from_rows",
    PHASE2_SCRIPT_PATH,
)
assert phase2_spec is not None
phase2_module = importlib.util.module_from_spec(phase2_spec)
assert phase2_spec.loader is not None
sys.modules[phase2_spec.name] = phase2_module
phase2_spec.loader.exec_module(phase2_module)


ACTIVE_ISM = """\
CCO 100001 CHEMBL1
c1ccccc1 100002 CHEMBL2
"""

DECOY_ISM = """\
CCN D0001
CCCC D0002
"""


def test_build_dude_enrichment_rows_uses_official_refs_and_label_independent_score() -> None:
    payload = module.build_dude_enrichment_rows(
        active_source=ACTIVE_ISM.encode("utf-8"),
        decoy_source=DECOY_ISM.encode("utf-8"),
        target_id="AA2AR",
        target_slug="aa2ar",
        active_limit=1,
        decoy_limit=2,
        active_ref="actives_final.ism",
        decoy_ref="decoys_final.ism",
    )

    target = payload["targets"][0]
    molecules = target["scored_molecules"]

    assert payload["schema_version"] == module.SCHEMA_VERSION
    assert payload["source_urls"]["target_page"] == (
        "https://dude.docking.org/targets/aa2ar/"
    )
    assert payload["source_checksums"]["combined_source"].startswith("sha256:")
    assert target["benchmark_family"] == "DUD-E"
    assert target["target_id"] == "AA2AR"
    assert target["score_direction"] == "higher_is_better"
    assert target["source_checksum"] == payload["source_checksums"]["combined_source"]
    assert target["selected_row_counts"] == {"active": 1, "decoy": 2}
    assert payload["score_policy"] == {
        "score_method": module.SCORE_METHOD,
        "score_direction": "higher_is_better",
        "label_independent": True,
        "uses_active_decoy_label_for_score": False,
    }
    assert [row["is_active"] for row in molecules] == [True, False, False]
    assert len({row["molecule_id"] for row in molecules}) == len(molecules)
    assert all(0.0 <= row["score"] <= 1.0 for row in molecules)
    assert all(row["score_method"] == module.SCORE_METHOD for row in molecules)
    assert "smiles" not in molecules[0]


def test_dude_enrichment_rows_feed_partial_phase2_audit(tmp_path: Path) -> None:
    actives_path = tmp_path / "actives_final.ism"
    decoys_path = tmp_path / "decoys_final.ism"
    rows_out = tmp_path / "public_benchmark_enrichment_rows.json"
    actives_path.write_text(ACTIVE_ISM, encoding="utf-8")
    decoys_path.write_text(DECOY_ISM, encoding="utf-8")

    exit_code = module.main(
        [
            "--actives-path",
            str(actives_path),
            "--decoys-path",
            str(decoys_path),
            "--active-limit",
            "1",
            "--decoy-limit",
            "2",
            "--out",
            str(rows_out),
        ]
    )
    audit = phase2_module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        enrichment_rows_path=rows_out,
        out_dir=tmp_path / "out",
        operator_bundle_out=tmp_path / "operator_bundle.json",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )
    scorecard = json.loads(
        (
            tmp_path
            / "out"
            / phase2_module.harness_bundle.ARTIFACT_FILENAMES[
                "enrichment_scorecard"
            ]
        ).read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert audit["phase2_ready"] is False
    assert audit["component_ready_count"] == 1
    assert "dud_e_or_lit_pcba_enrichment_ready" not in (
        audit["phase2_exit_gate"]["failed_criteria"]
    )
    assert scorecard["public_benchmark_enrichment_ready"] is True
    assert scorecard["real_enrichment_target_count"] == 1
