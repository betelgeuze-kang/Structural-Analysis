from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / ".github/workflows/_technical-evidence-attest.yml"
CALLERS = (
    ROOT / ".github/workflows/medium-scale-current-source.yml",
    ROOT / ".github/workflows/ifc-import-health-current-source.yml",
    ROOT / ".github/workflows/mgt-import-health-current-source.yml",
    ROOT / ".github/workflows/mgt-import-health-tenth-source.yml",
    ROOT / ".github/workflows/native-frame-alpha-clean-install.yml",
)
HASH_BOUND_FILES = (
    "src/structural_analysis/schemas/medium_scale_current_source_execution_v1.schema.json",
    "canonical/ifc-import-health-current-source-technical-receipt.v1.schema.json",
    "canonical/buildingsmart-ifc-current-source-manifest.v1.schema.json",
    "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json",
    "canonical/mgt-import-health-current-source-technical-receipt.v1.schema.json",
    "canonical/mgt-import-health-current-source-manifest.v1.schema.json",
    "benchmarks/import_health/mgt_current_source.v1.json",
    "canonical/mgt-import-health-tenth-source-technical-receipt.v1.schema.json",
    "canonical/mgt-import-health-tenth-source-manifest.v1.schema.json",
    "benchmarks/import_health/mgt_tenth_source_supplement.v1.json",
    "native/distribution/frame_alpha_clean_install_replay_v1.schema.json",
    "native/distribution/frame_alpha_clean_install_cross_platform_v1.schema.json",
    "native/distribution/frame_alpha_packaged_browser_replay_v1.schema.json",
    "native/distribution/frame_alpha_portable_install_state_v1.schema.json",
    "native/distribution/frame_alpha_portable_transition_replay_v1.schema.json",
    "native/distribution/frame_alpha_workstation_distribution_manifest_v2.schema.json",
)


def _inline_verifier(source: str) -> str:
    workflow = yaml.safe_load(source)
    run = workflow["jobs"]["verify-attest"]["steps"][0]["run"]
    marker = "python3 -I - <<'PY'\n"
    return run.split(marker, 1)[1].rsplit("\nPY", 1)[0]


def _schema_validator_from_inline():
    inline = _inline_verifier(VERIFIER.read_text(encoding="utf-8"))
    parsed = ast.parse(inline)
    wanted = {
        "SchemaContractError",
        "schema_error",
        "schema_json_equal",
        "resolve_schema_ref",
        "validate_schema_instance",
    }
    definitions = [
        node
        for node in parsed.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted
    ]
    namespace = {"re": re, "urlsplit": urlsplit}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(VERIFIER), "exec"), namespace)
    return namespace["validate_schema_instance"], namespace["SchemaContractError"]


def _strict_json_from_inline():
    inline = _inline_verifier(VERIFIER.read_text(encoding="utf-8"))
    parsed = ast.parse(inline)
    wanted = {
        "fail",
        "require",
        "unique_object",
        "reject_constant",
        "require_finite",
        "strict_json_bytes",
    }
    definitions = [
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {"json": json, "math": math}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(VERIFIER), "exec"), namespace)
    return namespace["strict_json_bytes"]


def test_privileged_verifier_has_no_repository_execution_step_and_compiles() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    job = source.split("jobs:", 1)[1]
    inline = _inline_verifier(source)

    compile(inline, f"{VERIFIER}:inline", "exec")
    assert "uses: actions/checkout" not in job
    assert "uses: actions/setup-python" not in job
    assert "uses: actions/setup-node" not in job
    assert "pip install" not in job
    assert "npm ci" not in job
    assert "scripts/" not in job
    assert "class NoRedirect(HTTPRedirectHandler)" in inline
    assert 'run.get("run_attempt") == int(run_attempt)' in inline
    assert 'producer_job_identity_invalid' in inline
    assert 'artifact_archive_digest_mismatch' in inline
    assert 'artifact_duplicate_path' in inline
    assert 'artifact_symlink_forbidden' in inline
    assert 'handoff_seal_file_set_mismatch' in inline
    assert 'validate_schema_instance(receipt, schema)' in inline
    assert 'strict_json_documents = {' in inline
    assert 'if path.suffix == ".json"' in inline
    assert 'ifc_support_file_hash_invalid' in inline
    assert 'mgt9_parser_report_hash_invalid' in inline
    assert 'mgt10_core_report_binding_invalid' in inline
    assert "subject-path: |" not in job
    assert "subject-path: ${{ runner.temp }}/verified-technical-handoff/${{ inputs.receipt-path }}" in job
    assert "subject-path: *" not in job


def test_every_canonical_schema_and_manifest_identity_is_hash_bound() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    for relative in HASH_BOUND_FILES:
        encoded = (ROOT / relative).read_bytes()
        assert hashlib.sha256(encoded).hexdigest() in source, relative


def test_privileged_schema_validator_enforces_schema_valued_additional_properties() -> None:
    validate, schema_error = _schema_validator_from_inline()
    schema = {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0},
    }

    validate({"ROW": 3}, schema)
    for invalid in ({"ROW": "3"}, {"ROW": -1}, {"ROW": True}):
        try:
            validate(invalid, schema)
        except schema_error:
            pass
        else:
            raise AssertionError(f"schema-valued additionalProperties accepted: {invalid}")


def test_privileged_strict_json_rejects_duplicate_and_nonfinite_numbers() -> None:
    strict_json = _strict_json_from_inline()
    assert strict_json(b'{"metric":1}', "attack") == {"metric": 1}

    attacks = (
        b'{"metric":1,"metric":2}',
        b'{"metric":NaN}',
        b'{"metric":Infinity}',
        b'{"metric":1e9999}',
    )
    for raw in attacks:
        try:
            strict_json(raw, "attack")
        except SystemExit:
            pass
        else:
            raise AssertionError(f"privileged strict JSON accepted: {raw!r}")


def test_callers_hand_off_artifact_id_and_digest_from_unprivileged_job() -> None:
    for path in CALLERS:
        source = path.read_text(encoding="utf-8")
        assert "name: produce-unprivileged" in source, path
        producer = source.split("name: produce-unprivileged", 1)[1].split(
            "\n  attest", 1
        )[0]
        assert 'GH_TOKEN: ""' in producer, path
        assert "id-token: write" not in producer, path
        assert "attestations: write" not in producer, path
        assert "artifact-metadata: write" not in producer, path
        assert "artifact-id: ${{ steps.handoff.outputs.artifact-id }}" in source, path
        assert "artifact-digest: ${{ steps.handoff.outputs.artifact-digest }}" in source, path
        assert "uses: ./.github/workflows/_technical-evidence-attest.yml" in source, path


def test_all_external_actions_are_immutable_full_sha_pins() -> None:
    action = re.compile(r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$")
    for path in (*CALLERS, VERIFIER):
        uses = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("uses: actions/")
        ]
        assert uses, path
        assert all(action.fullmatch(line) for line in uses), path
