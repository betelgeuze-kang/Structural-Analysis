from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_gpcr_hard_decoy_operator_template_from_rows.py"
SUITE_SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_gpcr_hard_decoy_suite_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_gpcr_hard_decoy_operator_template_from_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

suite_spec = importlib.util.spec_from_file_location(
    "materialize_gpcr_hard_decoy_suite_report",
    SUITE_SCRIPT_PATH,
)
assert suite_spec is not None
suite_module = importlib.util.module_from_spec(suite_spec)
assert suite_spec.loader is not None
sys.modules[suite_spec.name] = suite_module
suite_spec.loader.exec_module(suite_module)


def _write_csv(path: Path, *, targets: tuple[str, ...] = ("DRD2", "HTR2A", "OPRM1")) -> None:
    lines = ["target_id,molecule_id,score,is_positive,is_decoy,score_direction"]
    for target_id in targets:
        lines.extend(
            [
                f"{target_id},{target_id.lower()}_positive,0.9,true,false,higher_is_better",
                f"{target_id},{target_id.lower()}_decoy,0.1,false,true,higher_is_better",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, *, targets: tuple[str, ...] = ("DRD2", "HTR2A", "OPRM1")) -> None:
    rows: list[dict[str, object]] = []
    for target_id in targets:
        rows.extend(
            [
                {
                    "target_id": target_id,
                    "molecule_id": f"{target_id.lower()}_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": target_id,
                    "molecule_id": f"{target_id.lower()}_decoy",
                    "score": 0.1,
                    "is_positive": False,
                    "is_decoy": True,
                    "score_direction": "higher_is_better",
                },
            ]
        )
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_materializes_operator_template_from_flat_csv_rows(tmp_path: Path) -> None:
    rows = tmp_path / "gpcr_rows.csv"
    _write_csv(rows)

    payload = module.build_gpcr_hard_decoy_operator_template_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        source_id="operator_attached_gpcr_rows_csv",
        source_url="https://zenodo.org/records/1234567",
        source_license="CC-BY-4.0",
    )

    assert payload["schema_version"] == "gpcr-hard-decoy-operator-intake.v1"
    assert payload["operator_input_source"]["mode"] == "raw_hard_decoy_rows"
    assert payload["operator_input_source"]["row_count"] == 6
    assert payload["operator_input_source"]["accepted_target_row_count"] == 6
    assert payload["operator_input_source"]["missing_targets"] == []
    assert payload["operator_input_source"]["target_row_counts"] == {
        "DRD2": 2,
        "HTR2A": 2,
        "OPRM1": 2,
    }
    drd2 = payload["targets"][0]
    assert drd2["target_id"] == "DRD2"
    assert drd2["score_direction"] == "higher_is_better"
    assert drd2["hard_decoy_rows"] == [
        {
            "is_decoy": False,
            "is_positive": True,
            "molecule_id": "drd2_positive",
            "score": 0.9,
        },
        {
            "is_decoy": True,
            "is_positive": False,
            "molecule_id": "drd2_decoy",
            "score": 0.1,
        },
    ]
    report = suite_module.materialize_gpcr_hard_decoy_suite_report(
        payload,
        repo_root=REPO_ROOT,
    )
    assert report["status"] == "locked"
    assert report["broad_gpcr_family_claim_safe"] is False
    assert report["phase3_exit_gate"]["failed_criteria"] == [
        "raw_hard_decoy_rows_actual_closure"
    ]
    assert "DRD2:hard_decoy_rows_positive_count_below_actual_closure_minimum" in report[
        "blockers"
    ]


def test_materializes_operator_template_from_jsonl_rows(tmp_path: Path) -> None:
    rows = tmp_path / "gpcr_rows.jsonl"
    _write_jsonl(rows)

    payload = module.build_gpcr_hard_decoy_operator_template_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        source_id="operator_attached_gpcr_rows_jsonl",
        source_url="https://zenodo.org/records/1234567",
        source_license="CC-BY-4.0",
    )

    assert payload["operator_input_source"]["supported_source_formats"] == [
        "csv",
        "tsv",
        "json",
        "jsonl",
        "ndjson",
    ]
    assert payload["operator_input_source"]["row_count"] == 6
    assert payload["operator_input_source"]["accepted_target_row_count"] == 6

    report = suite_module.materialize_gpcr_hard_decoy_suite_report(
        payload,
        repo_root=REPO_ROOT,
    )
    assert report["status"] == "locked"
    assert report["broad_gpcr_family_claim_safe"] is False
    assert report["phase3_exit_gate"]["failed_criteria"] == [
        "raw_hard_decoy_rows_actual_closure"
    ]


def test_blocks_placeholder_molecule_ids(tmp_path: Path) -> None:
    rows = tmp_path / "gpcr_rows.jsonl"
    rows.write_text(
        "\n".join(
            json.dumps(row, sort_keys=True)
            for row in [
                {
                    "target_id": "DRD2",
                    "molecule_id": "fixture_drd2_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": "HTR2A",
                    "molecule_id": "htr2a_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": "OPRM1",
                    "molecule_id": "oprm1_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        module.build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:fixture_drd2_positive:molecule_id_placeholder"
    else:
        raise AssertionError("expected placeholder molecule id error")


def test_blocks_duplicate_molecule_ids_per_target(tmp_path: Path) -> None:
    rows = tmp_path / "gpcr_rows.jsonl"
    rows.write_text(
        "\n".join(
            json.dumps(row, sort_keys=True)
            for row in [
                {
                    "target_id": "DRD2",
                    "molecule_id": "drd2_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": "DRD2",
                    "molecule_id": "drd2_positive",
                    "score": 0.1,
                    "is_positive": False,
                    "is_decoy": True,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": "HTR2A",
                    "molecule_id": "htr2a_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
                {
                    "target_id": "OPRM1",
                    "molecule_id": "oprm1_positive",
                    "score": 0.9,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        module.build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "DRD2:drd2_positive:molecule_id_duplicate"
    else:
        raise AssertionError("expected duplicate molecule id error")


def test_blocks_missing_required_targets_unless_allowed(tmp_path: Path) -> None:
    rows = tmp_path / "gpcr_rows.csv"
    _write_csv(rows, targets=("DRD2",))

    try:
        module.build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "missing_required_gpcr_targets:HTR2A,OPRM1"
    else:
        raise AssertionError("expected missing target error")

    payload = module.build_gpcr_hard_decoy_operator_template_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        allow_missing_targets=True,
    )
    assert payload["operator_input_source"]["missing_targets"] == ["HTR2A", "OPRM1"]
    assert payload["targets"][1]["hard_decoy_rows"] is None


def test_cli_writes_operator_template_when_missing_targets_are_allowed(
    tmp_path: Path,
) -> None:
    rows = tmp_path / "gpcr_rows.csv"
    _write_csv(rows, targets=("DRD2",))
    out = tmp_path / "gpcr_hard_decoy_operator_template.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--rows", str(rows), "--out", str(out)]) == 2
    assert not out.exists()
    assert module.main(
        [
            "--repo-root",
            str(REPO_ROOT),
            "--rows",
            str(rows),
            "--out",
            str(out),
            "--allow-missing-targets",
        ]
    ) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["operator_input_source"]["missing_targets"] == ["HTR2A", "OPRM1"]
