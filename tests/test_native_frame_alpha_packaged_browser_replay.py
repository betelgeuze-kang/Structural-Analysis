from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (
        ROOT / "native/distribution/frame_alpha_packaged_browser_replay_v1.schema.json"
    ).read_text(encoding="utf-8")
)


def _receipt() -> dict[str, object]:
    return {
        "schema_version": "structural-frame-alpha-packaged-browser-replay.v1",
        "status": "pass",
        "source": {
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
            "binding_profile": "verified_clean_git_checkout.v1",
        },
        "platform_tag": "linux-x86_64-gnu",
        "package": {
            "package_id": "structural-frame-alpha-workstation-0.1.0-linux-x86_64-gnu",
            "manifest_sha256": "sha256:" + "1" * 64,
            "binary_sha256": "sha256:" + "2" * 64,
            "workbench_index_sha256": "sha256:" + "3" * 64,
        },
        "browser": {
            "engine": "chromium",
            "version": "141.0.7390.37",
            "route": "/#/workbench-v2",
            "packaged_static_files_only": True,
        },
        "execution": {
            "job_id": "job_" + "4" * 32,
            "job_view_sha256": "sha256:" + "5" * 64,
            "bundle_manifest_sha256": "sha256:" + "6" * 64,
            "model_ir_sha256": "sha256:" + "9" * 64,
            "result_ir_sha256": "sha256:" + "7" * 64,
            "result_hash": "sha256:" + "8" * 64,
            "elapsed_ms": 250,
        },
        "checks": {
            "model_file_uploaded": True,
            "same_origin_job_submitted": True,
            "native_worker_succeeded": True,
            "bundle_integrity_verified_in_browser": True,
            "result_ir_verified_in_browser": True,
            "selected_load_binding_verified": True,
            "model_result_bindings_verified": True,
            "numerical_gates_passed": True,
            "receipt_schema_validated_before_write": True,
            "release_authority_remained_blocked": True,
            "page_error_count": 0,
        },
        "authority": {
            "packaged_browser_execution": "passed",
            "human_new_user_observation": "not_evaluated",
            "accessibility_review": "not_evaluated",
            "os_code_signing": "not_evaluated",
            "automatic_update": "not_implemented",
            "rollback": "not_implemented",
            "engineering_design": "not_authoritative",
            "commercial_use": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": "one_packaged_workbench_chromium_upload_submit_run_poll_and_verified_result_replay_not_human_observation_accessibility_code_signing_update_rollback_or_release_authority",
    }


def test_packaged_browser_receipt_schema_accepts_only_bounded_browser_credit() -> None:
    Draft202012Validator(SCHEMA).validate(_receipt())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("human_new_user_observation", "passed"),
        ("accessibility_review", "passed"),
        ("os_code_signing", "passed"),
        ("release_readiness", "authoritative"),
    ],
)
def test_packaged_browser_schema_rejects_authority_promotion(
    field: str, value: str
) -> None:
    payload = deepcopy(_receipt())
    payload["authority"][field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(payload)


@pytest.mark.parametrize("elapsed_ms", [0, 180001])
def test_packaged_browser_schema_rejects_elapsed_outside_runtime_budget(
    elapsed_ms: int,
) -> None:
    payload = deepcopy(_receipt())
    payload["execution"]["elapsed_ms"] = elapsed_ms
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(payload)


@pytest.mark.parametrize(
    "check",
    [
        "selected_load_binding_verified",
        "model_result_bindings_verified",
        "receipt_schema_validated_before_write",
    ],
)
def test_packaged_browser_schema_rejects_missing_execution_proof(check: str) -> None:
    payload = deepcopy(_receipt())
    payload["checks"][check] = False
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(payload)


def test_packaged_browser_result_contract_rejects_binding_substitution() -> None:
    module_uri = (
        ROOT / "scripts/verify-native-frame-packaged-browser.mjs"
    ).resolve().as_uri()
    script = f"""
      import {{ validateBrowserResultContract }} from {json.dumps(module_uri)};
      const sha = (digit) => `sha256:${{digit.repeat(64)}}`;
      const valid = () => ({{
        model: {{ model_id: 'frame-alpha-distribution-cantilever' }},
        view: {{ model_content_hash: sha('1') }},
        bundle: {{
          schema_version: 'structural-native-linear-frame3d-workbench-bundle.v1',
          status: 'complete',
          artifacts: {{ model_ir: {{ content_hash: sha('1') }} }},
          bindings: {{
            model_content_hash: sha('1'),
            result_id: 'result.browser.LC_WEAK',
            result_hash: sha('4'),
          }},
        }},
        result: {{
          schema_version: 'structural-native-linear-frame3d-result-ir.v1',
          result_id: 'result.browser.LC_WEAK',
          result_hash: sha('4'),
          bindings: {{
            model_id: 'frame-alpha-distribution-cantilever',
            model_content_hash: sha('1'),
            model_semantic_hash: sha('2'),
            model_provenance_hash: sha('3'),
            load_pattern_id: 'LC_WEAK',
            load_combination_id: null,
          }},
          gates: {{
            native_residual_gate_passed: true,
            global_resultant_gate_passed: true,
            independent_recovery_replay_passed: true,
            fallback_count: 0,
            regularization_count: 0,
          }},
          authority: {{ release_readiness: 'not_authoritative' }},
        }},
        pageErrors: [],
      }});
      validateBrowserResultContract(valid());
      const attacks = [
        (value) => {{ value.result.bindings.load_pattern_id = 'LC_OTHER'; }},
        (value) => {{ value.result.bindings.load_combination_id = 'COMB1'; }},
        (value) => {{ value.result.bindings.model_id = 'other-model'; }},
        (value) => {{ value.view.model_content_hash = sha('f'); }},
        (value) => {{ value.bundle.artifacts.model_ir.content_hash = sha('f'); }},
        (value) => {{ value.bundle.bindings.result_id = 'result.other'; }},
        (value) => {{ value.bundle.bindings.result_hash = sha('f'); }},
      ];
      for (const mutate of attacks) {{
        const value = valid();
        mutate(value);
        let rejected = false;
        try {{
          validateBrowserResultContract(value);
        }} catch (error) {{
          rejected = String(error).includes('browser_result_contract_invalid');
        }}
        if (!rejected) throw new Error('binding_substitution_was_accepted');
      }}
    """
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_packaged_browser_script_uses_real_loopback_and_integrity_paths() -> None:
    source = (ROOT / "scripts/verify-native-frame-packaged-browser.mjs").read_text(
        encoding="utf-8"
    )
    for required in (
        "[data-native-frame-model-file]",
        "[data-native-frame-run-submit]",
        '[data-native-frame-run="succeeded"]',
        "bundle_verified",
        "result_ir_hash_mismatch",
        "model_ir_hash_mismatch",
        "global_resultant_gate_passed",
        "release_readiness",
        "writeValidatedReceipt",
    ):
        assert required in source
    assert "const maxHostRequests = 1024" in source
    assert "const maxReceiptElapsedMs = 180000" in source
    assert source.index("await validateReceiptAgainstSchema(receipt)") < source.index(
        "await writeFile(output"
    )
    assert "page.route(" not in source
    assert "route.fulfill(" not in source
