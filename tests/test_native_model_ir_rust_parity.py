from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structural_analysis.model_ir import (  # noqa: E402
    DuplicateJSONKeyError,
    canonicalize_model_ir_v2,
    load_json_object_strict,
    model_ir_v2_content_hash,
    model_ir_v2_provenance_hash,
    model_ir_v2_semantic_hash,
    validate_model_ir_v2,
)


FIXTURES = (
    Path("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
    Path("examples/bounded_planar_frame_alpha.model-ir.v2.json"),
    Path("examples/bounded_planar_settlement.model-ir.v2.json"),
    Path("examples/bounded_frame3d_direct_control.model-ir.v2.json"),
    Path("examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"),
    Path("examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json"),
    Path("examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json"),
    Path("examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json"),
)


def _rust_dump(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--manifest-path",
            "native/Cargo.toml",
            "-p",
            "structural-contracts",
            "--example",
            "modelir_contract_dump",
            "--",
            *(str(path) for path in paths),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _build_native_cli() -> Path:
    completed = subprocess.run(
        [
            "cargo",
            "build",
            "--quiet",
            "--locked",
            "--manifest-path",
            "native/Cargo.toml",
            "-p",
            "structural-cli",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = ROOT / "native" / "target" / "debug" / f"structural-cli{suffix}"
    assert executable.is_file()
    return executable


def _native_validation_report(executable: Path, path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(executable), "model", "validate", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode in {0, 2}, completed.stderr
    assert completed.stderr == ""
    report = json.loads(completed.stdout)
    assert isinstance(report, dict)
    return report


def _semantic_parity_cases(baseline: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    def changed(name: str) -> dict[str, Any]:
        payload = deepcopy(baseline)
        cases.append((name, payload))
        return payload

    unit_scale = changed("unit-scale")
    unit_scale["provenance"]["unit_scales_to_si"]["length_to_m"] = 10.0

    dangling_node = changed("dangling-node")
    dangling_node["elements"][0]["node_ids"][1] = "MISSING"

    same_nodes = changed("same-end-nodes")
    same_nodes["elements"][0]["node_ids"] = ["N1", "N1"]

    zero_length = changed("zero-effective-length")
    zero_length["elements"][0]["offsets"]["j_global_m"] = [-2.0, 0.0, 0.0]

    prescribed = changed("prescribed-not-restrained")
    prescribed["constraints"][0]["dofs"].remove("UX")

    all_zero = changed("all-zero-load")
    all_zero["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = 0.0

    cycle = changed("load-combination-cycle")
    cycle["load_combinations"] = [
        {
            "id": "CA",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "CB", "ref_kind": "load_combination", "factor": 1.0}
            ],
            "source_id": None,
            "extensions": {},
        },
        {
            "id": "CB",
            "index": 1,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "CA", "ref_kind": "load_combination", "factor": 1.0}
            ],
            "source_id": None,
            "extensions": {},
        },
    ]

    non_monotonic = changed("time-not-monotonic")
    non_monotonic["time_functions"] = [
        {
            "id": "TF",
            "index": 0,
            "type": "piecewise_linear",
            "points": [[1.0, 0.0], [1.0, 1.0]],
            "extensions": {},
        }
    ]

    roundtrip_kind = changed("roundtrip-kind")
    roundtrip_kind["roundtrip_map"] = [
        {
            "source_entity_id": "source:N1",
            "entity_kind": "material",
            "model_ir_entity_id": "N1",
            "mapping_status": "exact",
            "extensions": {},
        }
    ]

    stage_references = changed("stage-references")
    stage_references["construction_stages"] = [
        {
            "id": "ST",
            "index": 0,
            "active_element_ids": ["BAD_ELEMENT"],
            "active_constraint_ids": ["BAD_CONSTRAINT"],
            "load_pattern_ids": ["BAD_PATTERN"],
            "extensions": {},
        }
    ]

    duplicate_constraint = changed("duplicate-constraint")
    duplicate = deepcopy(duplicate_constraint["constraints"][0])
    duplicate["id"] = "BC2"
    duplicate["index"] = 1
    duplicate_constraint["constraints"].append(duplicate)

    duplicate_nested_load = changed("duplicate-nested-load")
    duplicate_nested_load["load_patterns"][1]["nodal_loads"][0]["id"] = (
        duplicate_nested_load["load_patterns"][0]["nodal_loads"][0]["id"]
    )

    explicit_blocker = changed("explicit-blocker")
    explicit_blocker["unsupported_features"] = [
        {
            "feature_id": "feature.blocked",
            "kind": "unsupported_solver_feature",
            "source_entity_id": None,
            "disposition": "blocked",
            "blocking": True,
            "detail": "Blocked for cross-language parity.",
            "extensions": {},
        }
    ]

    derived_blocker = changed("derived-blocker")
    derived_blocker["roundtrip_map"] = [
        {
            "source_entity_id": "source:N1",
            "entity_kind": "node",
            "model_ir_entity_id": "N1",
            "mapping_status": "unsupported",
            "extensions": {},
        }
    ]

    unicode_source = changed("unicode-source")
    unicode_source["provenance"]["source_ref"] = "구조/α/モデル.mgt"

    signed_zero = changed("signed-zero")
    signed_zero["coordinate_system"]["origin_m"][0] = -0.0
    return cases


def test_rust_canonical_bytes_and_three_hashes_match_python_oracle(
    tmp_path: Path,
) -> None:
    baseline = load_json_object_strict(ROOT / FIXTURES[0])
    signed_zero = deepcopy(baseline)
    signed_zero["coordinate_system"]["origin_m"][0] = -0.0
    signed_zero_path = tmp_path / "signed-zero.model-ir.v2.json"
    _write_json(signed_zero_path, signed_zero)
    generated_paths = [signed_zero_path]
    for index, number in enumerate(
        (1.0, 1e-4, 1e-5, 1e-6, 1.2345678901234567, 1e20),
        start=1,
    ):
        numeric = deepcopy(baseline)
        numeric["nodes"][1]["coordinates_m"][0] = number
        numeric_path = tmp_path / f"numeric-{index}.model-ir.v2.json"
        _write_json(numeric_path, numeric)
        generated_paths.append(numeric_path)
    unicode_payload = deepcopy(baseline)
    unicode_payload["provenance"]["source_ref"] = "구조/α/モデル.mgt"
    unicode_path = tmp_path / "unicode.model-ir.v2.json"
    _write_json(unicode_path, unicode_payload)
    generated_paths.append(unicode_path)
    paths = [*FIXTURES, *generated_paths]

    completed = _rust_dump(paths)

    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(rows) == len(paths)
    for path, row in zip(paths, rows, strict=True):
        resolved = path if path.is_absolute() else ROOT / path
        payload = load_json_object_strict(resolved)
        canonical = canonicalize_model_ir_v2(payload)
        assert row == {
            "path": str(path),
            "schema_valid": True,
            "model_id": payload["model_id"],
            "capability_profile": payload["capability_profile"],
            "canonical_json": canonical,
            "canonical_length": len(canonical.encode("utf-8")),
            "content_hash": model_ir_v2_content_hash(payload),
            "semantic_hash": model_ir_v2_semantic_hash(payload),
            "provenance_hash": model_ir_v2_provenance_hash(payload),
            "claim_boundary": (
                "rust_wire_identity_not_cpp_semantics_or_solver_readiness"
            ),
        }


def test_rust_cpp_roundtrip_and_semantic_issue_sets_match_python_oracle(
    tmp_path: Path,
) -> None:
    executable = _build_native_cli()
    baseline = load_json_object_strict(ROOT / FIXTURES[0])
    cases = [
        (path.stem, load_json_object_strict(ROOT / path)) for path in FIXTURES
    ]
    verified = load_json_object_strict(ROOT / FIXTURES[1])
    verified["capability_profile"] = "planar_frame_verified_alpha.v1"
    cases.append(("planar-frame-verified-profile", verified))
    cases.extend(_semantic_parity_cases(baseline))

    for index, (name, payload) in enumerate(cases):
        path = tmp_path / f"{index:02d}-{name}.model-ir.v2.json"
        _write_json(path, payload)
        python_report = validate_model_ir_v2(payload)
        assert python_report.schema_valid is True, name

        native_report = _native_validation_report(executable, path)
        native_issue_set = {
            (str(issue["code"]), str(issue["path"]))
            for issue in native_report["issues"]
        }
        python_issue_set = {
            (issue.code, issue.path) for issue in python_report.issues
        }

        assert native_report["model_ir_schema_version"] == python_report.schema_version, name
        assert native_report["schema_valid"] == python_report.schema_valid, name
        assert native_report["semantics_valid"] == python_report.semantics_valid, name
        assert native_report["contract_valid"] == python_report.contract_valid, name
        assert native_report["analysis_ready"] == python_report.analysis_ready, name
        assert native_issue_set == python_issue_set, name
        assert native_report["blocking_feature_ids"] == list(
            python_report.blocking_feature_ids
        ), name
        assert native_report["derived_blocking_feature_ids"] == list(
            python_report.derived_blocking_feature_ids
        ), name
        assert native_report["content_hash"] == python_report.content_hash, name
        assert native_report["semantic_hash"] == python_report.semantic_hash, name
        assert native_report["provenance_hash"] == python_report.provenance_hash, name


@pytest.mark.parametrize(
    ("case", "expected_rust_code"),
    (
        ("unknown_field", "model_ir_schema_invalid"),
        ("float_index", "model_ir_schema_invalid"),
        ("boolean_index", "model_ir_schema_invalid"),
        ("root_array", "model_ir_schema_invalid"),
        ("duplicate_key", "model_ir_duplicate_json_key"),
        ("nan", "model_ir_invalid_json"),
    ),
)
def test_rust_and_python_fail_closed_on_wire_negative_matrix(
    tmp_path: Path,
    case: str,
    expected_rust_code: str,
) -> None:
    payload: object = load_json_object_strict(ROOT / FIXTURES[0])
    path = tmp_path / f"{case}.json"
    if case == "unknown_field":
        assert isinstance(payload, dict)
        payload["elements"][0]["unknown_core_field"] = True
        _write_json(path, payload)
        assert validate_model_ir_v2(payload).schema_valid is False
    elif case == "float_index":
        assert isinstance(payload, dict)
        payload["nodes"][0]["index"] = 0.0
        _write_json(path, payload)
        assert validate_model_ir_v2(payload).schema_valid is False
    elif case == "boolean_index":
        assert isinstance(payload, dict)
        payload["nodes"][0]["index"] = True
        _write_json(path, payload)
        assert validate_model_ir_v2(payload).schema_valid is False
    elif case == "root_array":
        _write_json(path, [])
    elif case == "duplicate_key":
        path.write_text('{"id":1,"id":2}', encoding="utf-8")
        with pytest.raises(DuplicateJSONKeyError):
            load_json_object_strict(path)
    elif case == "nan":
        path.write_text('{"value":NaN}', encoding="utf-8")
        loaded = load_json_object_strict(path)
        assert validate_model_ir_v2(loaded).contract_valid is False
    else:  # pragma: no cover - parametrization invariant
        raise AssertionError(case)

    completed = _rust_dump([path])

    assert completed.returncode == 3
    error = json.loads(completed.stderr.splitlines()[-1])
    assert error["code"] == expected_rust_code
    assert error["path"] == "/"
