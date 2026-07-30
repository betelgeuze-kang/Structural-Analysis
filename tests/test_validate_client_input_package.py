from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "validate_client_input_package.py"
SPEC = importlib.util.spec_from_file_location("validate_client_input_package", SCRIPT_PATH)
assert SPEC is not None
validate_client_input_package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_client_input_package)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_client_input_validator_ready_case(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "model.json",
        {
            "model": {
                "nodes": [
                    {"id": "N1", "x": 0, "y": 0, "z": 0},
                    {"id": "N2", "x": 0, "y": 0, "z": 1},
                ],
                "elements": [{"id": "E1", "i": "N1", "j": "N2"}],
                "metadata": {"units": {"length": "m", "force": "kN"}, "revision": "A"},
                "loads": {"DL": []},
            }
        },
    )

    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path)

    assert payload["schema_version"] == "client-input-validation-report.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["reason_codes"] == ["PASS"]
    assert payload["checks"]["coordinates_valid"] is True
    assert payload["checks"]["data_files_parse"] is True
    assert payload["input_binding"]["file_count"] == 1
    assert payload["input_binding"]["current_worktree_bound"] is False
    assert payload["input_binding"]["commit_tree_bound"] is False
    assert payload["artifact_hash"].startswith("sha256:")


def test_client_input_validator_needs_review_for_missing_units(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "model.json",
        {
            "nodes": [
                {"id": "N1", "x": 0, "y": 0, "z": 0},
                {"id": "N2", "x": 0, "y": 0, "z": 1},
            ],
            "elements": [{"id": "E1", "i": "N1", "j": "N2"}],
        },
    )

    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path)

    assert payload["status"] == "needs_review"
    assert payload["contract_pass"] is False
    assert "unit_information_missing" in payload["needs_review"]
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_UNITS_MISSING"


def test_client_input_validator_blocks_missing_package(tmp_path: Path) -> None:
    payload = validate_client_input_package.validate_client_input_package(input_path=tmp_path / "missing")

    assert payload["status"] == "blocked"
    assert "input_package_missing_or_empty" in payload["blockers"]
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_MISSING_OR_EMPTY"


def test_client_input_validator_blocks_malformed_json(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text("{", encoding="utf-8")

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["status"] == "blocked"
    assert "data_file_parse_failed" in payload["blockers"]
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_DATA_FILE_PARSE_FAILED"


def test_client_input_validator_rejects_zip_path_escape(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.json", "{}")

    payload = validate_client_input_package.validate_client_input_package(
        input_path=archive_path
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["unsafe_archive_path"]
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_UNSAFE_ARCHIVE_PATH"


def test_client_input_validator_rejects_nested_directory_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "model.json").write_text("{}", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["input_symlink_rejected"]
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_SYMLINK"


def test_client_input_validator_accepts_strict_multifile_csv_topology(
    tmp_path: Path,
) -> None:
    (tmp_path / "nodes.csv").write_text(
        "node_id,x,y,z,units,load_case,revision\n"
        "N1,0,0,0,m,DL,A\n"
        "N2,0,0,3,m,DL,A\n",
        encoding="utf-8",
    )
    (tmp_path / "members.csv").write_text(
        "member_id,i,j\nE1,N1,N2\n",
        encoding="utf-8",
    )

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["status"] == "ready"
    assert payload["checks"]["topology_valid"] is True


@pytest.mark.parametrize(
    ("filename", "contents"),
    (
        ("invalid-utf8.csv", b"node_id,x,y,z\nN1,0,0,\xff\n"),
        ("ragged.csv", b"node_id,x,y,z\nN1,0,0\n"),
        ("unmatched.csv", b'node_id,x,y,z\n"N1,0,0,0\n'),
    ),
)
def test_client_input_validator_blocks_each_malformed_csv_independently(
    tmp_path: Path,
    filename: str,
    contents: bytes,
) -> None:
    (tmp_path / filename).write_bytes(contents)
    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_DATA_FILE_PARSE_FAILED"


def test_client_input_validator_blank_csv_metadata_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.csv").write_text(
        "node_id,x,y,z,member_id,i,j,units,load_case,revision\n"
        "N1,0,0,0,,,,,,\n"
        "N2,0,0,3,E1,N1,N2,,,\n",
        encoding="utf-8",
    )

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["contract_pass"] is False
    assert "unit_information_missing" in payload["needs_review"]
    assert "load_case_or_combination_missing" in payload["needs_review"]
    assert "revision_information_missing" in payload["needs_review"]


def test_client_input_validator_blocks_orphan_and_zero_length_members(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.csv").write_text(
        "node_id,x,y,z,member_id,i,j,units,load_case,revision\n"
        "N1,0,0,0,,,,m,DL,A\n"
        "N2,0,0,0,E1,N1,N2,m,DL,A\n"
        ",,,,E2,,,m,DL,A\n",
        encoding="utf-8",
    )

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_CLIENT_INPUT_TOPOLOGY_INVALID"


def test_client_input_validator_scans_rows_beyond_one_thousand(
    tmp_path: Path,
) -> None:
    nodes = [
        {"id": f"N{index}", "x": float(index), "y": 0.0, "z": 0.0}
        for index in range(1001)
    ]
    _write_json(
        tmp_path / "model.json",
        {
            "nodes": nodes,
            "elements": [{"id": "E1", "i": "N999", "j": "N1000"}],
            "units": {"length": "m", "force": "kN"},
            "load_case": "DL",
            "revision": "A",
        },
    )

    payload = validate_client_input_package.validate_client_input_package(
        input_path=tmp_path
    )

    assert payload["status"] == "ready"
    assert payload["checks"]["topology_valid"] is True
