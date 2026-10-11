"""Exercise the isolated privileged parser, without executing repository code."""

from __future__ import annotations

import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ".ci/product-state-inputs/"
REPORT_PATHS = (
    PREFIX + "post-main-overlay-attestation-verification.json",
    PREFIX + "opensees-calculix-clean-runner/attestation-verification.json",
    PREFIX
    + "opensees-calculix-clean-runner/artifacts/vv/opensees_calculix_clean_runner/clean_runner_handoff.attestation-verification.json",
    *(
        PREFIX + "bounded-planar-supplemental-attestations/" + family + "/" + suffix
        for family, producer in (
            ("linear", "bounded-planar-opensees"),
            ("negative", "bounded-planar-negative-opensees"),
            ("scaling", "bounded-planar-scaling-opensees"),
            ("modal_buckling", "bounded-planar-modal-buckling"),
            (
                "nonlinear_material_recovery",
                "bounded-planar-nonlinear-material-recovery",
            ),
        )
        for suffix in (
            "product-state-attestation-verification.json",
            f"artifact/.ci/{producer}/attestation-verification.json",
        )
    ),
)


def _parser():
    workflow = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    start = workflow.index("          def fail(reason):")
    end = workflow.index("          def digest(raw):", start)
    source = textwrap.dedent(workflow[start:end])
    # Every executed node is one of the workflow's isolated parser helpers.
    assert all(isinstance(node, ast.FunctionDef) for node in ast.parse(source).body)
    namespace = {"json": json, "math": math}
    exec(compile(source, "privileged-candidate-json-parser", "exec"), namespace)
    return namespace


def _report():
    # Synthetic envelope only: never represents an authentic attestation.
    return [
        {
            "attestation": {"bundle": {"synthetic": True}},
            "verificationResult": {
                "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                "signature": {"certificate": {"synthetic": True}},
                "statement": {"synthetic": True},
                "verifiedTimestamps": [{"synthetic": True}],
            },
        }
    ]


@pytest.mark.parametrize("name", REPORT_PATHS)
def test_candidate_accepts_only_named_report_envelopes(name):
    report = _report()
    assert _parser()["load_candidate_json"](json.dumps(report), name) == report


@pytest.mark.parametrize(
    "name",
    (
        "product-state-candidate.seal.json",
        "artifacts/manifests/product_state.current.v1.json",
        "canonical/product-authority-profiles.v1.json",
        PREFIX + "nightly-artifacts.json",
        PREFIX + "unrecognized/attestation-verification.json",
        REPORT_PATHS[0] + ".json",
        REPORT_PATHS[0].replace("post-main", "unknown"),
        REPORT_PATHS[-1].replace("nonlinear_material_recovery", "linear"),
    ),
)
def test_other_candidate_json_still_requires_objects(name):
    load = _parser()["load_candidate_json"]
    assert load(b'{"ok": true}', name) == {"ok": True}
    for value in (_report(), [], None, True, 1, "text"):
        with pytest.raises(SystemExit, match="json_object_required"):
            load(json.dumps(value), name)


@pytest.mark.parametrize(
    "value", ({}, [], [None], [{}], [_report()[0]] * 2, None, 1, True, "text")
)
def test_report_requires_singleton_object_envelope(value):
    with pytest.raises(SystemExit, match="candidate_attestation_report_shape_invalid"):
        _parser()["load_candidate_json"](json.dumps(value), REPORT_PATHS[0])


@pytest.mark.parametrize(
    "field,value",
    (
        ("attestation", None),
        ("attestation.bundle", []),
        ("attestation.bundle", {}),
        ("verificationResult", None),
        ("verificationResult.mediaType", "wrong"),
        ("verificationResult.signature", None),
        ("verificationResult.signature.certificate", {}),
        ("verificationResult.statement", []),
        ("verificationResult.statement", {}),
        ("verificationResult.verifiedTimestamps", []),
        ("verificationResult.verifiedTimestamps", [None]),
    ),
)
def test_report_rejects_malformed_nested_envelope(field, value):
    report = deepcopy(_report())
    target = report[0]
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(SystemExit, match="candidate_attestation_report_shape_invalid"):
        _parser()["load_candidate_json"](json.dumps(report), REPORT_PATHS[0])


@pytest.mark.parametrize("name", (REPORT_PATHS[0], "product-state-candidate.seal.json"))
@pytest.mark.parametrize(
    "raw,error",
    (
        (b'{"a":1,"a":2}', "duplicate_json_key"),
        (b'[{"a":{"x":1,"x":2}}]', "duplicate_json_key"),
        (b'[{"a":NaN}]', "nonfinite_json_number"),
        (b'[{"a":Infinity}]', "nonfinite_json_number"),
        (b'[{"a":-Infinity}]', "nonfinite_json_number"),
        (b'[{"a":1e999}]', "nonfinite_json_number"),
        (b'[{"a":-1e999}]', "nonfinite_json_number"),
        (b"{} trailing", "strict_json_invalid"),
        (b"\xff", "strict_json_invalid"),
    ),
)
def test_candidate_keeps_strict_parsing(name, raw, error):
    with pytest.raises(SystemExit, match=error):
        _parser()["load_candidate_json"](raw, name)


def test_object_loader_does_not_infer_array_permission_from_name():
    with pytest.raises(SystemExit, match="json_object_required"):
        _parser()["load"](json.dumps(_report()), REPORT_PATHS[0])


def test_seal_loop_uses_parser_after_verifying_original_bytes():
    workflow = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    assert 'if name.endswith(".json"): load_candidate_json(raw, name)' in workflow
    assert workflow.index('row["sha256"] != digest(raw)') < workflow.index(
        'if name.endswith(".json"): load_candidate_json(raw, name)'
    )
