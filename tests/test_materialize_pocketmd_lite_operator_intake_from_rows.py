from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_pocketmd_lite_operator_intake_from_rows.py"
SURVIVAL_SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_pocketmd_lite_topk_survival_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_operator_intake_from_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

survival_spec = importlib.util.spec_from_file_location(
    "materialize_pocketmd_lite_topk_survival_report",
    SURVIVAL_SCRIPT_PATH,
)
assert survival_spec is not None
survival_module = importlib.util.module_from_spec(survival_spec)
assert survival_spec.loader is not None
sys.modules[survival_spec.name] = survival_module
survival_spec.loader.exec_module(survival_module)


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(case_id: str, candidate_id: str) -> str:
    return (
        "https://zenodo.org/records/7654321/files/"
        f"pocketmd-lite-{case_id}-{candidate_id}.json#row"
    )


def _row(
    *,
    case_id: str,
    candidate_id: str,
    top_k_rank: int,
    local_min_survived: bool,
    contact_rate: float,
    h_bond_rate: float,
    clash_before: int,
    clash_after: int,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind operator intake",
        "top_k_rank": top_k_rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": -8.0 + top_k_rank,
        "post_refinement_energy_proxy": -8.5 + top_k_rank,
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_interval": {
            "low": -0.1,
            "high": 0.3,
            "unit": "energy_proxy_delta",
        },
        "provenance_ref": _provenance_ref(case_id, candidate_id),
        "source_checksum": _checksum(f"{case_id}:{candidate_id}"),
    }


def _write_csv(path: Path) -> None:
    header = [
        "case_id",
        "source_family",
        "top_k_rank",
        "candidate_id",
        "pre_refinement_energy_proxy",
        "post_refinement_energy_proxy",
        "local_min_survived",
        "contact_persistence_rate",
        "h_bond_persistence_rate",
        "clash_count_before",
        "clash_count_after",
        "uncertainty_low",
        "uncertainty_high",
        "uncertainty_unit",
        "provenance_ref",
        "source_checksum",
    ]
    rows = [
        [
            "case_a",
            "CASF/PDBBind operator intake",
            "1",
            "pose_1",
            "-8.0",
            "-8.5",
            "true",
            "0.8",
            "0.6",
            "4",
            "1",
            "-0.2",
            "0.2",
            "energy_proxy_delta",
            _provenance_ref("case_a", "pose_1"),
            _checksum("case_a:pose_1"),
        ],
        [
            "case_a",
            "CASF/PDBBind operator intake",
            "2",
            "pose_2",
            "-7.0",
            "-7.5",
            "false",
            "0.7",
            "0.4",
            "2",
            "2",
            "0.1",
            "0.3",
            "energy_proxy_delta",
            _provenance_ref("case_a", "pose_2"),
            _checksum("case_a:pose_2"),
        ],
        [
            "case_b",
            "CASF/PDBBind operator intake",
            "1",
            "pose_1",
            "-9.0",
            "-9.2",
            "true",
            "1.0",
            "0.9",
            "5",
            "3",
            "-0.1",
            "0.7",
            "energy_proxy_delta",
            _provenance_ref("case_b", "pose_1"),
            _checksum("case_b:pose_1"),
        ],
        [
            "case_b",
            "CASF/PDBBind operator intake",
            "2",
            "pose_2",
            "-7.0",
            "-7.5",
            "false",
            "0.7",
            "0.4",
            "2",
            "2",
            "0.1",
            "0.3",
            "energy_proxy_delta",
            _provenance_ref("case_b", "pose_2"),
            _checksum("case_b:pose_2"),
        ],
        [
            "case_c",
            "CASF/PDBBind operator intake",
            "1",
            "pose_1",
            "-8.0",
            "-8.5",
            "true",
            "0.8",
            "0.6",
            "4",
            "1",
            "-0.2",
            "0.2",
            "energy_proxy_delta",
            _provenance_ref("case_c", "pose_1"),
            _checksum("case_c:pose_1"),
        ],
        [
            "case_c",
            "CASF/PDBBind operator intake",
            "2",
            "pose_2",
            "-7.0",
            "-7.5",
            "false",
            "0.7",
            "0.4",
            "2",
            "2",
            "0.1",
            "0.3",
            "energy_proxy_delta",
            _provenance_ref("case_c", "pose_2"),
            _checksum("case_c:pose_2"),
        ],
    ]
    lines = [",".join(header), *[",".join(row) for row in rows]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_materializes_operator_intake_from_flat_csv_rows(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.csv"
    _write_csv(rows)

    payload = module.build_pocketmd_lite_operator_intake_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        source_id="operator_attached_pocketmd_lite_rows_csv",
        source_url="https://zenodo.org/records/7654321",
        source_license="CC-BY-4.0",
    )

    assert payload["schema_version"] == "pocketmd-lite-operator-intake.v1"
    assert payload["operator_input_source"]["mode"] == "raw_top_k_refinement_rows"
    assert payload["operator_input_source"]["source_url"] == (
        "https://zenodo.org/records/7654321"
    )
    assert payload["operator_input_source"]["source_license"] == "CC-BY-4.0"
    assert payload["operator_input_source"]["row_count"] == 6
    assert payload["operator_input_source"]["case_count"] == 3
    assert payload["operator_input_source"]["top_k_candidate_count"] == 6
    assert payload["operator_input_source"]["case_row_counts"] == {
        "case_a": 2,
        "case_b": 2,
        "case_c": 2,
    }
    assert payload["operator_input_source"]["top_k_rank_prefix_policy"].startswith(
        "For each case, supplied ranks must form a contiguous prefix"
    )
    assert payload["operator_input_source"]["top_k_scope_policy"] == (
        "Operator import is bounded to supplied upstream top-k candidates; "
        "top_k_rank must be between 1 and 20."
    )
    assert payload["operator_input_source"]["case_top_k_rank_prefixes"] == {
        "case_a": [1, 2],
        "case_b": [1, 2],
        "case_c": [1, 2],
    }
    assert payload["operator_input_source"]["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    row_contract = payload["operator_input_source"]["row_value_contract"]
    assert row_contract["top_k_rank_policy"].startswith(
        "top_k_rank must parse to a positive integer not exceeding max_top_k (20)"
    )
    assert row_contract["rate_value_policy"] == {
        "contact_persistence_rate": "must parse to a finite fraction from 0.0 to 1.0",
        "h_bond_persistence_rate": "must parse to a finite fraction from 0.0 to 1.0",
    }
    assert row_contract["uncertainty_interval_policy"].startswith(
        "uncertainty_interval or uncertainty_low/high must parse to finite numbers"
    )
    assert payload["operator_input_source"]["source_receipt_requirements"][
        "required_fields"
    ] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact",
        "source_artifact_sha256",
    ]
    assert payload["cases"][0]["top_k_rank"] == 1
    assert payload["cases"][0]["local_min_survived"] is True
    assert payload["cases"][0]["uncertainty_interval"] == {
        "low": -0.2,
        "high": 0.2,
        "unit": "energy_proxy_delta",
    }

    report = survival_module.materialize_pocketmd_lite_topk_survival_report(
        payload,
        repo_root=REPO_ROOT,
    )
    assert report["status"] == "ready"
    assert report["product_surface_ready"] is True
    assert report["phase4_exit_gate"]["failed_criteria"] == []


def test_materializes_operator_intake_from_nested_json_rows(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    rows.write_text(
        json.dumps(
            {
                "top_k_refinement_rows": [
                    _row(
                        case_id="case_json",
                        candidate_id="pose_json",
                        top_k_rank=1,
                        local_min_survived=True,
                        contact_rate=0.9,
                        h_bond_rate=0.5,
                        clash_before=3,
                        clash_after=1,
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = module.build_pocketmd_lite_operator_intake_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        max_top_k=5,
    )

    assert payload["cases"] == [
        _row(
            case_id="case_json",
            candidate_id="pose_json",
            top_k_rank=1,
            local_min_survived=True,
            contact_rate=0.9,
            h_bond_rate=0.5,
            clash_before=3,
            clash_after=1,
        )
    ]
    assert payload["operator_input_source"]["row_value_contract"][
        "top_k_rank_policy"
    ].startswith(
        "top_k_rank must parse to a positive integer not exceeding max_top_k (5)"
    )


def test_materializes_operator_intake_from_ndjson_rows(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.ndjson"
    _write_jsonl(
        rows,
        [
            _row(
                case_id="case_ndjson_a",
                candidate_id="pose_1",
                top_k_rank=1,
                local_min_survived=True,
                contact_rate=0.9,
                h_bond_rate=0.8,
                clash_before=4,
                clash_after=1,
            ),
            _row(
                case_id="case_ndjson_a",
                candidate_id="pose_2",
                top_k_rank=2,
                local_min_survived=True,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=3,
                clash_after=2,
            ),
            _row(
                case_id="case_ndjson_b",
                candidate_id="pose_1",
                top_k_rank=1,
                local_min_survived=True,
                contact_rate=0.9,
                h_bond_rate=0.8,
                clash_before=4,
                clash_after=1,
            ),
            _row(
                case_id="case_ndjson_b",
                candidate_id="pose_2",
                top_k_rank=2,
                local_min_survived=True,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=3,
                clash_after=2,
            ),
            _row(
                case_id="case_ndjson_c",
                candidate_id="pose_1",
                top_k_rank=1,
                local_min_survived=True,
                contact_rate=0.9,
                h_bond_rate=0.8,
                clash_before=4,
                clash_after=1,
            ),
            _row(
                case_id="case_ndjson_c",
                candidate_id="pose_2",
                top_k_rank=2,
                local_min_survived=True,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=3,
                clash_after=2,
            ),
        ],
    )

    payload = module.build_pocketmd_lite_operator_intake_from_rows(
        rows_path=rows,
        repo_root=REPO_ROOT,
        source_id="operator_attached_pocketmd_lite_rows_ndjson",
        source_url="https://zenodo.org/records/7654321",
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
    assert payload["operator_input_source"]["case_count"] == 3

    report = survival_module.materialize_pocketmd_lite_topk_survival_report(
        payload,
        repo_root=REPO_ROOT,
    )
    assert report["status"] == "ready"
    assert report["operator_input_source_receipt"]["contract_pass"] is True
    assert report["product_surface_ready"] is True
    assert report["phase4_exit_gate"]["failed_criteria"] == []


def test_blocks_placeholder_row_identifiers(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.jsonl"
    row = _row(
        case_id="case_a",
        candidate_id="pose_1",
        top_k_rank=1,
        local_min_survived=True,
        contact_rate=0.9,
        h_bond_rate=0.8,
        clash_before=4,
        clash_after=1,
    )
    row["source_family"] = "fixture benchmark source"
    _write_jsonl(rows, [row])

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:case_a:source_family_placeholder"
    else:
        raise AssertionError("expected placeholder source family error")


def test_blocks_invalid_checksum_and_non_topk_rank(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    bad_row = _row(
        case_id="case_bad",
        candidate_id="pose_bad",
        top_k_rank=21,
        local_min_survived=True,
        contact_rate=0.9,
        h_bond_rate=0.5,
        clash_before=3,
        clash_after=1,
    )
    bad_row["source_checksum"] = "sha256:not-a-real-digest"
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert "source_checksum_invalid" in str(exc)
    else:
        raise AssertionError("expected invalid checksum error")

    bad_row["source_checksum"] = _checksum("case_bad:pose_bad")
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")
    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:case_bad:top_k_rank_exceeds_max:20"
    else:
        raise AssertionError("expected max top-k error")


def test_blocks_non_finite_numeric_values(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    bad_row = _row(
        case_id="case_bad",
        candidate_id="pose_bad",
        top_k_rank=1,
        local_min_survived=True,
        contact_rate=0.9,
        h_bond_rate=0.5,
        clash_before=3,
        clash_after=1,
    )
    bad_row["contact_persistence_rate"] = "nan"
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:contact_persistence_rate_invalid"
    else:
        raise AssertionError("expected non-finite contact rate error")

    bad_row["contact_persistence_rate"] = 0.9
    bad_row["uncertainty_interval"] = {
        "low": 0.0,
        "high": "Infinity",
        "unit": "energy_proxy_delta",
    }
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:uncertainty_interval_invalid"
    else:
        raise AssertionError("expected non-finite uncertainty interval error")


def test_blocks_native_json_non_finite_numeric_values(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    bad_row = _row(
        case_id="case_bad",
        candidate_id="pose_bad",
        top_k_rank=1,
        local_min_survived=True,
        contact_rate=0.9,
        h_bond_rate=0.5,
        clash_before=3,
        clash_after=1,
    )
    bad_row["pre_refinement_energy_proxy"] = float("inf")
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:pre_refinement_energy_proxy_invalid"
    else:
        raise AssertionError("expected non-finite energy proxy error")

    bad_row["pre_refinement_energy_proxy"] = -7.0
    bad_row["uncertainty_interval"] = {
        "low": 0.0,
        "high": float("nan"),
        "unit": "energy_proxy_delta",
    }
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:uncertainty_interval_invalid"
    else:
        raise AssertionError("expected native non-finite uncertainty interval error")


def test_blocks_non_contiguous_topk_rank_prefix(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    rows.write_text(
        json.dumps(
            [
                _row(
                    case_id="case_gap",
                    candidate_id="pose_1",
                    top_k_rank=1,
                    local_min_survived=True,
                    contact_rate=0.9,
                    h_bond_rate=0.5,
                    clash_before=3,
                    clash_after=1,
                ),
                _row(
                    case_id="case_gap",
                    candidate_id="pose_3",
                    top_k_rank=3,
                    local_min_survived=True,
                    contact_rate=0.9,
                    h_bond_rate=0.5,
                    clash_before=3,
                    clash_after=1,
                ),
            ]
        ),
        encoding="utf-8",
    )

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "case_gap:top_k_rank_prefix_gap:2"
    else:
        raise AssertionError("expected top-k rank prefix gap error")


def test_blocks_placeholder_row_receipts(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.json"
    bad_row = _row(
        case_id="case_bad",
        candidate_id="pose_bad",
        top_k_rank=1,
        local_min_survived=True,
        contact_rate=0.9,
        h_bond_rate=0.5,
        clash_before=3,
        clash_after=1,
    )
    bad_row["provenance_ref"] = "operator://case_bad/pose_bad"
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")

    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:case_bad:provenance_ref_placeholder"
    else:
        raise AssertionError("expected placeholder provenance error")

    bad_row["provenance_ref"] = "local-evidence://pocketmd-lite/case_bad/pose_bad"
    bad_row["source_checksum"] = _checksum("case_bad:pose_bad")
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")
    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:case_bad:provenance_ref_placeholder"
    else:
        raise AssertionError("expected local evidence provenance error")

    bad_row["provenance_ref"] = _provenance_ref("case_bad", "pose_bad")
    bad_row["source_checksum"] = "sha256:" + "a" * 64
    rows.write_text(json.dumps([bad_row]), encoding="utf-8")
    try:
        module.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows,
            repo_root=REPO_ROOT,
        )
    except ValueError as exc:
        assert str(exc) == "row_1:case_bad:source_checksum_placeholder_digest"
    else:
        raise AssertionError("expected placeholder checksum error")


def test_cli_writes_operator_intake(tmp_path: Path) -> None:
    rows = tmp_path / "pocketmd_lite_rows.csv"
    out = tmp_path / "pocketmd_lite_operator_intake.json"
    _write_csv(rows)

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--rows",
                str(rows),
                "--out",
                str(out),
                "--source-id",
                "operator_attached_pocketmd_lite_rows_cli",
                "--source-url",
                "https://zenodo.org/records/7654321",
                "--source-license",
                "CC-BY-4.0",
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["operator_input_source"]["source_id"] == (
        "operator_attached_pocketmd_lite_rows_cli"
    )
    assert len(payload["cases"]) == 6
