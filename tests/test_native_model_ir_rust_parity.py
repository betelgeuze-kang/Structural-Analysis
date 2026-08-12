from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

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
