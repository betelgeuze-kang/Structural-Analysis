from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_native_frame3d_modelir_parity.py"
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v1.schema.json"
)


@pytest.fixture(scope="module")
def parity_receipt_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    temporary = tmp_path_factory.mktemp("native-frame3d-modelir-parity")
    target = temporary / "cargo-target"
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(ROOT / "native/Cargo.toml"),
            "--package",
            "structural-cli",
            "--locked",
            "--target-dir",
            str(target),
        ],
        cwd=ROOT,
        check=True,
        timeout=600,
    )
    executable = target / "debug/structural-cli"
    outputs = [temporary / "first.json", temporary / "second.json"]
    for output in outputs:
        subprocess.run(
            [
                "python3",
                str(RUNNER),
                "--structural-cli",
                str(executable),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
            timeout=60,
        )
    first = outputs[0].read_bytes()
    assert first == outputs[1].read_bytes()
    return first


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_parity_pack_is_deterministic_schema_valid_and_feature_complete(
    parity_receipt_bytes: bytes,
) -> None:
    payload = json.loads(parity_receipt_bytes)
    _validator().validate(payload)

    assert [case["case_id"] for case in payload["cases"]] == [
        "rotated_offset_mixed_load",
        "released_uniform_member_load",
        "nested_linear_combination",
    ]
    features = {feature for case in payload["cases"] for feature in case["features"]}
    assert {
        "self_weight",
        "rigid_end_offset",
        "rotational_release",
        "nested_linear_combination",
    } <= features
    assert payload["authority"] == {
        "implementation_verification": "bounded_cross_implementation",
        "external_code_comparison": "not_evaluated",
        "experimental_validation": "not_established",
        "engineering_design": "not_authoritative",
        "release_readiness": "not_authoritative",
    }


def test_parity_pack_schema_rejects_authority_promotion(
    parity_receipt_bytes: bytes,
) -> None:
    promoted = deepcopy(json.loads(parity_receipt_bytes))
    promoted["authority"]["release_readiness"] = "authoritative"

    with pytest.raises(ValidationError):
        _validator().validate(promoted)
