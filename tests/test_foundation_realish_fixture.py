from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "foundation_realish"
FIXTURE_SPECS = [
    {
        "stem": "foundation_small",
        "node_count": 8,
        "element_count": 3,
        "group_row_count": 2,
        "foundation_group_name": "FOUNDATION_ZONE",
        "frame_group_name": "PERIM_FRAME",
        "foundation_element_ids": [101, 102],
        "frame_element_ids": [103],
        "foundation_count": 2,
        "beam_count": 1,
        "foundation_sections": {"RAFT-1200", "PILE-CAP-700"},
    },
    {
        "stem": "foundation_deep_small",
        "node_count": 10,
        "element_count": 4,
        "group_row_count": 2,
        "foundation_group_name": "DEEP_FOUNDATION_ZONE",
        "frame_group_name": "UPPER_FRAME",
        "foundation_element_ids": [201, 202, 203],
        "frame_element_ids": [204],
        "foundation_count": 3,
        "beam_count": 1,
        "foundation_sections": {"MAT-1500", "CAISSON-900", "PILE-600"},
    },
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / name


def _run_parser_fixture(tmp_path: Path, *, fixture_name: str = "foundation_small.mgt") -> tuple[Path, Path]:
    model_out = tmp_path / "parsed_foundation_model.json"
    report_out = tmp_path / "parsed_foundation_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/parse_midas_mgt_to_json_npz.py",
            "--mgt",
            str(_fixture_path(fixture_name)),
            "--json-out",
            str(model_out),
            "--npz-out",
            str(tmp_path / "parsed_foundation_model.npz"),
            "--edge-list-out",
            str(tmp_path / "parsed_foundation_edges.json"),
            "--report-out",
            str(report_out),
            "--min-nodes",
            "4",
            "--min-elements",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return model_out, report_out


def _run_dataset_fixture(
    tmp_path: Path,
    *,
    model_path: Path | None = None,
    fixture_stem: str = "foundation_small",
) -> tuple[Path, Path]:
    dataset_out = tmp_path / "design_optimization_dataset_report.json"
    npz_out = tmp_path / "design_optimization_dataset.npz"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_path or _fixture_path(f"{fixture_stem}_model.json")),
            "--code-check",
            str(_fixture_path(f"{fixture_stem}_code_check.json")),
            "--pbd-review",
            str(_fixture_path(f"{fixture_stem}_pbd.json")),
            "--ndtha-residual",
            str(_fixture_path(f"{fixture_stem}_ndtha.json")),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(dataset_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return dataset_out, npz_out


def _run_foundation_artifact_and_report(
    *,
    tmp_path: Path,
    dataset_out: Path,
    npz_out: Path,
    model_path: Path,
) -> tuple[dict, dict]:
    dataset = _load_json(dataset_out)
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert foundation_rows
    first = foundation_rows[0]

    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"

    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": str(first.get("group_id", "")),
                    "member_type": str(first.get("member_type", "")),
                    "semantic_group": str(first.get("semantic_group", "")),
                    "action_name": "mat_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    artifact_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(npz_out),
            "--midas-model",
            str(model_path),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert artifact_proc.returncode == 0, artifact_proc.stderr

    report_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--foundation-optimization-artifact",
            str(artifact_out),
            "--out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_proc.returncode == 0, report_proc.stderr
    return _load_json(artifact_out), _load_json(report_out)


def _fixture_param_id(spec: dict) -> str:
    return str(spec["stem"])


@pytest.mark.parametrize("fixture_spec", FIXTURE_SPECS, ids=_fixture_param_id)
def test_foundation_realish_fixture_parses_raw_mgt_into_expected_groups(tmp_path: Path, fixture_spec: dict) -> None:
    model_out, report_out = _run_parser_fixture(tmp_path, fixture_name=f"{fixture_spec['stem']}.mgt")

    report = _load_json(report_out)
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["metrics"]["node_count"] == fixture_spec["node_count"]
    assert report["metrics"]["element_count"] == fixture_spec["element_count"]
    assert report["metrics"]["element_rows_skipped"] == 0
    assert report["metrics"]["group_row_count"] == fixture_spec["group_row_count"]

    model = _load_json(model_out)
    groups = model["model"]["metadata"]["groups"]
    assert len(groups) == 2
    foundation_group = next(group for group in groups if str(group.get("name")) == fixture_spec["foundation_group_name"])
    perimeter_group = next(group for group in groups if str(group.get("name")) == fixture_spec["frame_group_name"])
    assert foundation_group["element_ids"] == fixture_spec["foundation_element_ids"]
    assert perimeter_group["element_ids"] == fixture_spec["frame_element_ids"]


@pytest.mark.parametrize("fixture_spec", FIXTURE_SPECS, ids=_fixture_param_id)
def test_foundation_realish_fixture_promotes_scope_into_dataset(tmp_path: Path, fixture_spec: dict) -> None:
    dataset_out, _npz_out = _run_dataset_fixture(tmp_path, fixture_stem=str(fixture_spec["stem"]))

    report = _load_json(dataset_out)
    counts = report["summary"]["member_type_counts"]
    assert counts["foundation"] == fixture_spec["foundation_count"]
    assert counts["beam"] == fixture_spec["beam_count"]
    foundation_rows = [row for row in report["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == fixture_spec["foundation_count"]
    assert {str(row.get("semantic_group")) for row in foundation_rows} == {fixture_spec["foundation_group_name"]}
    assert {str(row.get("section_name")) for row in foundation_rows} == fixture_spec["foundation_sections"]


@pytest.mark.parametrize("fixture_spec", FIXTURE_SPECS, ids=_fixture_param_id)
def test_foundation_realish_fixture_drives_artifact_and_report(tmp_path: Path, fixture_spec: dict) -> None:
    dataset_out, npz_out = _run_dataset_fixture(tmp_path, fixture_stem=str(fixture_spec["stem"]))
    artifact, report = _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=dataset_out,
        npz_out=npz_out,
        model_path=_fixture_path(f"{fixture_spec['stem']}_model.json"),
    )
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["candidate_scan_mode"] == "npz_full"
    assert artifact["summary"]["foundation_member_type_count"] == fixture_spec["foundation_count"]
    assert artifact["summary"]["optimized_foundation_group_count"] == 1
    assert artifact["summary"]["raw_source_foundation_label_count"] > 0
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["foundation_member_type_count"] == fixture_spec["foundation_count"]
    assert report["summary"]["foundation_scope_source"] == "dataset_summary"


@pytest.mark.parametrize("fixture_spec", FIXTURE_SPECS, ids=_fixture_param_id)
def test_foundation_realish_fixture_closes_raw_mgt_to_report_path(tmp_path: Path, fixture_spec: dict) -> None:
    model_out, report_out = _run_parser_fixture(tmp_path, fixture_name=f"{fixture_spec['stem']}.mgt")
    parse_report = _load_json(report_out)
    assert parse_report["contract_pass"] is True
    assert parse_report["reason_code"] == "PASS"

    dataset_out, npz_out = _run_dataset_fixture(tmp_path, model_path=model_out, fixture_stem=str(fixture_spec["stem"]))
    dataset = _load_json(dataset_out)
    counts = dataset["summary"]["member_type_counts"]
    assert counts["foundation"] == fixture_spec["foundation_count"]
    assert counts["beam"] == fixture_spec["beam_count"]

    artifact, report = _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=dataset_out,
        npz_out=npz_out,
        model_path=model_out,
    )
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["foundation_member_type_count"] == fixture_spec["foundation_count"]
    assert artifact["summary"]["raw_source_foundation_label_count"] > 0
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["optimization_mode"] == "active_foundation_member_optimization"


def test_foundation_realish_generic_section_fixture_promotes_scope_via_group_tokens(tmp_path: Path) -> None:
    model_out, report_out = _run_parser_fixture(tmp_path, fixture_name="foundation_generic_sections.mgt")
    parse_report = _load_json(report_out)
    assert parse_report["contract_pass"] is True
    assert parse_report["reason_code"] == "PASS"

    model = _load_json(model_out)
    groups = {str(group.get("name")): group for group in model["model"]["metadata"]["groups"]}
    assert "PILE_FOUNDATION_ZONE" in groups
    assert groups["PILE_FOUNDATION_ZONE"]["element_ids"] == [101, 102]
    assert [str(section.get("name")) for section in model["model"]["sections"]] == ["DBUSER", "DBUSER", "B-SEC-450"]

    dataset_out, npz_out = _run_dataset_fixture(tmp_path, model_path=model_out)
    dataset = _load_json(dataset_out)
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 2
    assert {str(row.get("semantic_group")) for row in foundation_rows} == {"PILE_FOUNDATION_ZONE"}
    assert {str(row.get("section_name")) for row in foundation_rows} == {"DBUSER"}

    artifact, report = _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=dataset_out,
        npz_out=npz_out,
        model_path=model_out,
    )
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["foundation_member_type_count"] == 2
    assert artifact["summary"]["optimized_foundation_group_count"] == 1
    assert artifact["summary"]["upstream_generic_section_name_count"] == 2
    assert artifact["summary"]["upstream_foundation_label_count"] == 1
    assert artifact["summary"]["raw_source_foundation_label_count"] == 1
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["foundation_scope_source"] == "dataset_summary"


def test_foundation_realish_parser_drop_fixture_promotes_scope_via_parsed_plane_type(tmp_path: Path) -> None:
    model_out, report_out = _run_parser_fixture(tmp_path, fixture_name="foundation_parser_drop_small.mgt")
    parse_report = _load_json(report_out)
    assert parse_report["contract_pass"] is True
    assert parse_report["reason_code"] == "PASS"

    model = _load_json(model_out)
    groups = {str(group.get("name")): group for group in model["model"]["metadata"]["groups"]}
    assert set(groups) == {"SUBSTRUCT_ZONE", "PERIM_FRAME"}
    assert groups["SUBSTRUCT_ZONE"]["plane_type"] == "FOUNDATION"
    assert [str(section.get("name")) for section in model["model"]["sections"]] == ["DBUSER", "DBUSER", "B-SEC-450"]

    dataset_out, npz_out = _run_dataset_fixture(tmp_path, model_path=model_out)
    dataset = _load_json(dataset_out)
    counts = dataset["summary"]["member_type_counts"]
    assert counts["foundation"] == 2
    assert counts["beam"] == 1
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 2
    assert {str(row.get("semantic_group")) for row in foundation_rows} == {"SUBSTRUCT_ZONE"}
    assert {str(row.get("section_name")) for row in foundation_rows} == {"DBUSER"}

    artifact, report = _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=dataset_out,
        npz_out=npz_out,
        model_path=model_out,
    )
    assert artifact["contract_pass"] is True
    assert artifact["reason_code"] == "PASS"
    assert artifact["summary"]["foundation_member_type_count"] == 2
    assert artifact["summary"]["optimized_foundation_group_count"] == 1
    assert artifact["summary"]["raw_source_foundation_label_count"] == 1
    assert artifact["summary"]["upstream_foundation_label_count"] == 1
    assert artifact["summary"]["upstream_foundation_provenance_mode"] == "dataset_scope_only"
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["foundation_member_type_count"] == 2
    assert report["summary"]["foundation_scope_source"] == "dataset_summary"
