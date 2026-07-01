from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_enrichment_scorecard.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_enrichment_scorecard",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _target(
    *,
    benchmark_family: str,
    target_id: str,
    score_direction: str,
    scored_molecules: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "benchmark_family": benchmark_family,
        "target_id": target_id,
        "score_direction": score_direction,
        "scored_molecules": scored_molecules,
        "source_license_or_accession": f"{benchmark_family}:{target_id}",
        "source_checksum": _checksum(f"{benchmark_family}:{target_id}"),
        "provenance_ref": _provenance_ref(
            "public-benchmark",
            "enrichment",
            benchmark_family,
            f"{target_id}.json",
        ),
    }


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(*parts: str) -> str:
    return "https://zenodo.org/records/8642135/files/" + "/".join(parts)


def _molecule(molecule_id: str, *, is_active: bool, score: float) -> dict[str, object]:
    return {"molecule_id": molecule_id, "is_active": is_active, "score": score}


def _valid_intake() -> dict[str, object]:
    return {
        "targets": [
            _target(
                benchmark_family="DUD-E",
                target_id="aa2ar",
                score_direction="higher_is_better",
                scored_molecules=[
                    _molecule("active_1", is_active=True, score=0.90),
                    _molecule("active_2", is_active=True, score=0.70),
                    _molecule("decoy_1", is_active=False, score=0.40),
                    _molecule("decoy_2", is_active=False, score=0.10),
                ],
            ),
            _target(
                benchmark_family="LIT-PCBA",
                target_id="ESR1",
                score_direction="lower_is_better",
                scored_molecules=[
                    _molecule("active_1", is_active=True, score=0.10),
                    _molecule("decoy_1", is_active=False, score=0.20),
                    _molecule("decoy_2", is_active=False, score=0.30),
                    _molecule("decoy_3", is_active=False, score=0.40),
                ],
            ),
        ]
    }


def test_public_benchmark_enrichment_materializer_scores_targets() -> None:
    scorecard = module.materialize_enrichment_scorecard(_valid_intake(), repo_root=REPO_ROOT)

    assert scorecard["schema_version"] == "public-benchmark-enrichment-scorecard.v1"
    assert scorecard["status"] == "ready"
    assert scorecard["contract_pass"] is True
    assert scorecard["public_benchmark_enrichment_ready"] is True
    assert scorecard["real_enrichment_target_count"] == 2
    assert scorecard["benchmark_family_target_counts"] == {"DUD-E": 1, "LIT-PCBA": 1}
    assert scorecard["blockers"] == []
    assert scorecard["summary"] == {
        "active_count": 3,
        "benchmark_families": ["DUD-E", "LIT-PCBA"],
        "benchmark_family_count": 2,
        "benchmark_family_target_counts": {"DUD-E": 1, "LIT-PCBA": 1},
        "blocker_count": 0,
        "covered_supported_family_count": 2,
        "decoy_count": 5,
        "enrichment_factor_1pct_median": 3.0,
        "enrichment_factor_5pct_median": 3.0,
        "missing_supported_families": [],
        "molecule_count": 8,
        "ready_target_count": 2,
        "roc_auc_median": 1.0,
        "target_count": 2,
    }
    rows = {row["target_id"]: row for row in scorecard["target_rows"]}
    assert rows["aa2ar"]["enrichment_factor_1pct"] == 2.0
    assert rows["ESR1"]["enrichment_factor_1pct"] == 4.0
    assert rows["aa2ar"]["roc_auc"] == 1.0
    assert rows["ESR1"]["roc_auc"] == 1.0


def test_public_benchmark_enrichment_materializer_blocks_duplicate_row_identities() -> None:
    intake = json.loads(json.dumps(_valid_intake()))
    targets = intake["targets"]
    assert isinstance(targets, list)
    first_target = targets[0]
    assert isinstance(first_target, dict)
    molecules = first_target["scored_molecules"]
    assert isinstance(molecules, list)
    molecules.append(_molecule("active_1", is_active=True, score=0.95))
    targets.append(_target(
        benchmark_family="DUD-E",
        target_id="aa2ar",
        score_direction="higher_is_better",
        scored_molecules=[
            _molecule("active_3", is_active=True, score=0.88),
            _molecule("decoy_3", is_active=False, score=0.15),
        ],
    ))

    scorecard = module.materialize_enrichment_scorecard(intake, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["public_benchmark_enrichment_ready"] is False
    assert "aa2ar:molecule_4:molecule_id_duplicate:active_1" in scorecard["blockers"]
    assert "aa2ar:target_id_duplicate" in scorecard["blockers"]
    assert "row_integrity_required" in scorecard["root_cause_tags"]
    assert scorecard["row_integrity_policy"]["required_unique_row_keys"] == {
        "targets": ["target_id"],
        "target_scored_molecules": ["molecule_id"],
    }


def test_public_benchmark_enrichment_materializer_blocks_empty_intake() -> None:
    scorecard = module.materialize_enrichment_scorecard({"targets": []}, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["public_benchmark_enrichment_ready"] is False
    assert scorecard["first_blocked_target"] == "dud_e_lit_pcba_operator_intake"
    assert scorecard["root_cause_tags"] == ["operator_enrichment_rows_required"]
    assert scorecard["blockers"] == [
        "dud_e_lit_pcba_enrichment_targets_missing",
        "dud_e_lit_pcba_scored_molecules_missing",
        "dud_e_lit_pcba_active_decoy_labels_missing",
    ]


def test_public_benchmark_enrichment_materializer_blocks_bad_rows() -> None:
    scorecard = module.materialize_enrichment_scorecard(
        {
            "targets": [
                {
                    "benchmark_family": "unsupported",
                    "target_id": "bad_target",
                    "score_direction": "sideways",
                    "scored_molecules": [
                        {"molecule_id": "m1", "is_active": True, "score": "high"}
                    ],
                    "source_license_or_accession": "",
                    "source_checksum": "",
                    "provenance_ref": "",
                }
            ]
        },
        repo_root=REPO_ROOT,
    )

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["first_blocked_target"] == "bad_target"
    assert "bad_target:benchmark_family_unsupported" in scorecard["blockers"]
    assert "bad_target:score_direction_invalid" in scorecard["blockers"]
    assert "bad_target:molecule_0:score_invalid" in scorecard["blockers"]


def test_public_benchmark_enrichment_materializer_blocks_invalid_checksum() -> None:
    intake = _valid_intake()
    targets = intake["targets"]
    assert isinstance(targets, list)
    first_target = targets[0]
    assert isinstance(first_target, dict)
    first_target["source_checksum"] = "sha256:not-a-real-digest"

    scorecard = module.materialize_enrichment_scorecard(intake, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["first_blocked_target"] == "aa2ar"
    assert "aa2ar:source_checksum_invalid" in scorecard["blockers"]
    assert "operator_receipts_required" in scorecard["root_cause_tags"]


def test_public_benchmark_enrichment_materializer_blocks_placeholder_receipts() -> None:
    intake = _valid_intake()
    targets = intake["targets"]
    assert isinstance(targets, list)
    first_target = targets[0]
    assert isinstance(first_target, dict)
    first_target["source_license_or_accession"] = "DUD-E:test-accession"
    first_target["source_checksum"] = "sha256:" + "a" * 64
    first_target["provenance_ref"] = "operator://dud-e/aa2ar"

    scorecard = module.materialize_enrichment_scorecard(intake, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["first_blocked_target"] == "aa2ar"
    assert "aa2ar:source_license_or_accession_placeholder" in scorecard["blockers"]
    assert "aa2ar:source_checksum_placeholder_digest" in scorecard["blockers"]
    assert "aa2ar:provenance_ref_placeholder" in scorecard["blockers"]
    assert "operator_receipts_required" in scorecard["root_cause_tags"]


def test_public_benchmark_enrichment_materializer_blocks_local_proxy_receipts() -> None:
    intake = _valid_intake()
    targets = intake["targets"]
    assert isinstance(targets, list)
    first_target = targets[0]
    assert isinstance(first_target, dict)
    first_target["provenance_ref"] = "local-evidence://public-benchmark/dud-e/aa2ar"

    scorecard = module.materialize_enrichment_scorecard(intake, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["first_blocked_target"] == "aa2ar"
    assert "aa2ar:provenance_ref_placeholder" in scorecard["blockers"]
    assert "operator_receipts_required" in scorecard["root_cause_tags"]


def test_public_benchmark_enrichment_materializer_blocks_duplicate_row_identities() -> None:
    intake = _valid_intake()
    targets = intake["targets"]
    assert isinstance(targets, list)
    first_target = targets[0]
    second_target = targets[1]
    assert isinstance(first_target, dict)
    assert isinstance(second_target, dict)
    molecules = first_target["scored_molecules"]
    assert isinstance(molecules, list)
    molecules[1]["molecule_id"] = molecules[0]["molecule_id"]
    second_target["target_id"] = first_target["target_id"]

    scorecard = module.materialize_enrichment_scorecard(intake, repo_root=REPO_ROOT)

    assert scorecard["status"] == "operator_evidence_required"
    assert scorecard["contract_pass"] is False
    assert scorecard["public_benchmark_enrichment_ready"] is False
    assert scorecard["row_integrity_policy"]["required_unique_row_keys"] == {
        "targets": ["target_id"],
        "target_scored_molecules": ["molecule_id"],
    }
    assert "aa2ar:molecule_1:molecule_id_duplicate:active_1" in scorecard["blockers"]
    assert "aa2ar:target_id_duplicate" in scorecard["blockers"]
    assert "row_integrity_required" in scorecard["root_cause_tags"]


def test_public_benchmark_enrichment_materializer_cli_writes_scorecard_and_report(
    tmp_path: Path,
) -> None:
    intake = tmp_path / "enrichment_intake.json"
    intake.write_text(json.dumps(_valid_intake()), encoding="utf-8")
    out_scorecard = tmp_path / "public_benchmark_enrichment_scorecard.json"
    out_report = tmp_path / "public_benchmark_enrichment_materialization_report.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-scorecard",
                str(out_scorecard),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    scorecard = json.loads(out_scorecard.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert scorecard["public_benchmark_enrichment_ready"] is True
    assert report["public_benchmark_enrichment_ready"] is True
    assert scorecard["input_checksums"][
        "scripts/materialize_public_benchmark_enrichment_scorecard.py"
    ].startswith("sha256:")
    assert scorecard["input_checksums"][str(intake)].startswith("sha256:")


def test_public_benchmark_enrichment_materializer_cli_fail_blocked_returns_one(
    tmp_path: Path,
) -> None:
    intake = tmp_path / "empty_enrichment_intake.json"
    intake.write_text(json.dumps({"targets": []}), encoding="utf-8")
    out_scorecard = tmp_path / "public_benchmark_enrichment_scorecard.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-scorecard",
                str(out_scorecard),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 1
    )
    scorecard = json.loads(out_scorecard.read_text(encoding="utf-8"))
    assert scorecard["public_benchmark_enrichment_ready"] is False
