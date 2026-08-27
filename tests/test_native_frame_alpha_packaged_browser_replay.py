from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

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
            "numerical_gates_passed": True,
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
        "global_resultant_gate_passed",
        "release_readiness",
    ):
        assert required in source
    assert "page.route(" not in source
    assert "route.fulfill(" not in source
