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


def test_packaged_browser_terminal_classification_and_diagnostics_are_bounded() -> None:
    module_uri = (
        ROOT / "scripts/verify-native-frame-packaged-browser.mjs"
    ).resolve().as_uri()
    script = f"""
      import {{ createServer }} from 'node:http';
      import {{
        buildBrowserFailureDiagnostic,
        captureJobViewDiagnostic,
        classifyNativeFramePanelState,
        extractStableDiagnosticCode,
      }} from {json.dumps(module_uri)};
      const cases = [
        ['succeeded', false, 'succeeded'],
        ['failed', false, 'failed'],
        ['cancelled', false, 'cancelled'],
        ['running', true, 'timeout'],
        ['running', false, 'pending'],
      ];
      for (const [status, timedOut, expected] of cases) {{
        const actual = classifyNativeFramePanelState(status, {{ timedOut }});
        if (actual !== expected) throw new Error(`classification_invalid:${{status}}:${{actual}}`);
      }}
      for (const value of [
        `ghp_${{'a'.repeat(40)}}`,
        `github_pat_${{'b'.repeat(60)}}`,
        'Bearer standalone-secret',
      ]) {{
        if (extractStableDiagnosticCode(value) !== null) {{
          throw new Error(`secret_was_accepted_as_code:${{value}}`);
        }}
      }}
      if (extractStableDiagnosticCode('native_worker_failed: detail') !== 'native_worker_failed') {{
        throw new Error('native_error_code_was_rejected');
      }}
      const secret = `ghp_${{'A'.repeat(40)}}`;
      const diagnostic = buildBrowserFailureDiagnostic({{
        sourceCommit: 'a'.repeat(40),
        platformTag: 'linux-x86_64-gnu',
        phase: 'native_job_terminal_wait',
        panel: {{
          status: 'failed',
          jobText: `token=super-secret-value ${{'x'.repeat(10000)}}`,
          errorText: `Authorization: Bearer ${{secret}}`,
        }},
        submittedJobId: `job_${{'b'.repeat(32)}}`,
        jobView: {{ status: 'failed', errorCode: 'native_worker_failed' }},
        pageErrors: Array.from({{ length: 20 }}, (_, index) => `error-${{index}}-${{secret}}`),
        verifierError: `api_key=private-value ${{secret}}`,
        hostExitCode: 1,
        hostStderr: `password=hunter2 ${{'y'.repeat(10000)}}`,
        elapsedMs: 999999,
      }});
      const encoded = JSON.stringify(diagnostic);
      if (Buffer.byteLength(encoded, 'utf8') > 32768) throw new Error('diagnostic_too_large');
      if (diagnostic.page_errors.count !== 8 || !diagnostic.page_errors.overflow) {{
        throw new Error('page_error_limit_invalid');
      }}
      if (diagnostic.elapsed_ms !== 180000) throw new Error('elapsed_limit_invalid');
      for (const forbidden of [secret, 'super-secret-value', 'private-value', 'hunter2']) {{
        if (encoded.includes(forbidden)) throw new Error(`diagnostic_secret_leaked:${{forbidden}}`);
      }}
      if (diagnostic.panel.job_id !== `job_${{'b'.repeat(32)}}`) throw new Error('job_id_missing');
      if (diagnostic.job_view.status !== 'failed') throw new Error('job_view_status_missing');
      if (diagnostic.job_view.error_code !== 'native_worker_failed') {{
        throw new Error('job_view_error_code_missing');
      }}
      if (diagnostic.workstation.stderr_bytes > 2048 || diagnostic.verifier.error_bytes > 2048) {{
        throw new Error('diagnostic_text_limit_invalid');
      }}
      if (diagnostic.authority.release_readiness !== 'not_authoritative') {{
        throw new Error('diagnostic_authority_promoted');
      }}
      const submittedJobId = `job_${{'c'.repeat(32)}}`;
      let responseJobId = submittedJobId;
      const server = createServer((_request, response) => {{
        response.setHeader('content-type', 'application/json');
        response.end(JSON.stringify({{
          job_id: responseJobId,
          status: 'failed',
          error: {{ code: 'native_worker_failed', detail: secret }},
        }}));
      }});
      await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
      const address = server.address();
      if (!address || typeof address === 'string') throw new Error('diagnostic_server_invalid');
      const origin = `http://127.0.0.1:${{address.port}}`;
      const exact = await captureJobViewDiagnostic(origin, submittedJobId);
      if (exact.status !== 'failed' || exact.errorCode !== 'native_worker_failed') {{
        throw new Error('exact_job_view_diagnostic_invalid');
      }}
      responseJobId = `job_${{'d'.repeat(32)}}`;
      const mismatch = await captureJobViewDiagnostic(origin, submittedJobId);
      if (mismatch.status !== 'unavailable' || mismatch.errorCode !== null) {{
        throw new Error('mismatched_job_view_was_accepted');
      }}
      await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
    """
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_packaged_browser_failure_writes_only_bounded_non_authoritative_diagnostic(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "structural-frame-alpha-workstation-0.1.0-linux-x86_64-gnu"
    binary = package_root / "bin" / "structural-cli"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/usr/bin/env sh\nprintf '%s\\n' 'password=must-not-leak' >&2\nexit 1\n",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    model = package_root / "examples" / "frame-alpha-cantilever.model-ir.json"
    model.parent.mkdir(parents=True)
    model.write_bytes(
        (ROOT / "native/distribution/frame-alpha-cantilever.model-ir.json").read_bytes()
    )
    (package_root / "workbench").mkdir()
    source_commit = "a" * 40
    (package_root / "manifest.json").write_text(
        json.dumps(
            {
                "package_id": package_root.name,
                "platform_tag": "linux-x86_64-gnu",
                "source": {"commit_sha": source_commit, "tree_sha": "b" * 40},
                "binary": {"path": "bin/structural-cli"},
            }
        ),
        encoding="utf-8",
    )
    receipt_dir = tmp_path / "receipt"
    receipt_dir.mkdir()
    success_output = receipt_dir / "browser.json"
    completed = subprocess.run(
        [
            "node",
            "scripts/verify-native-frame-packaged-browser.mjs",
            "--package-root",
            str(package_root),
            "--source-commit",
            source_commit,
            "--platform-tag",
            "linux-x86_64-gnu",
            "--output",
            str(success_output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert not success_output.exists()
    failure_output = receipt_dir / "failure.json"
    diagnostic = json.loads(failure_output.read_text(encoding="utf-8"))
    serialized = json.dumps(diagnostic)
    assert diagnostic["phase"] == "host_startup"
    assert diagnostic["verifier"]["error_code"] == "host_exited_before_startup"
    assert diagnostic["workstation"]["stderr_bytes"] > 0
    assert diagnostic["authority"]["release_readiness"] == "not_authoritative"
    assert "must-not-leak" not in serialized
    assert failure_output.stat().st_size < 32768


def test_packaged_browser_script_uses_real_loopback_and_integrity_paths() -> None:
    source = (ROOT / "scripts/verify-native-frame-packaged-browser.mjs").read_text(
        encoding="utf-8"
    )
    for required in (
        "[data-native-frame-model-file]",
        "[data-native-frame-run-submit]",
        '[data-native-frame-run="succeeded"]',
        '[data-native-frame-run="failed"]',
        '[data-native-frame-run="cancelled"]',
        "browser_native_run_${panelOutcome}",
        "capturePanelDiagnostic",
        "captureJobViewDiagnostic",
        "page.on('request'",
        "request.postDataJSON()",
        "view.job_id !== jobId",
        "failure.json",
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
    assert "pageErrors.join" not in source
    assert "page_error_count=${pageErrors.length}" in source
