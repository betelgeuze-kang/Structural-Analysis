from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/g1-production-mgt-gfx1100-hardware.yml"
LFS_POINTER_VERSION = "version https://git-lfs.github.com/spec/v1"


def test_gfx1100_workflow_is_manual_and_dedicated() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw)
    trigger = payload.get("on", payload.get(True))
    assert set(trigger) == {"workflow_dispatch"}
    assert trigger["workflow_dispatch"] == {}
    job = payload["jobs"]["production-gfx1100"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "g1-production-gfx1100"
    assert job["runs-on"] == [
        "self-hosted",
        "linux",
        "x64",
        "amd",
        "rocm",
        "gfx1100",
        "g1-production-gfx1100",
    ]
    checkouts = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 2
    assert checkouts[0]["with"]["path"] == "control"
    assert checkouts[0]["with"]["ref"] == "${{ github.sha }}"
    assert checkouts[0]["with"]["lfs"] is True
    assert checkouts[1]["with"]["path"] == "source"
    assert checkouts[1]["with"]["ref"] == payload["env"]["EXPECTED_SOURCE_SHA"]
    assert all(step["with"]["persist-credentials"] is False for step in checkouts)
    assert "pull_request_target" not in raw
    assert "pull_request:" not in raw
    assert "push:" not in raw
    assert "inputs.source_sha" not in raw


def test_gfx1100_workflow_fails_closed_and_exports_evidence() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    for required in (
        'test "$GITHUB_REF" = "refs/heads/main"',
        'git -C "$CONTROL_ROOT" rev-parse HEAD',
        'git -C "$SOURCE_ROOT" rev-parse HEAD',
        'test "$INDEPENDENCE_ATTESTED" = "true"',
        'test "$EVIDENCE_RUNNER_ID" = "$EXPECTED_RUNNER_ID"',
        'test "$EVIDENCE_ORGANIZATION_ID" != "local-development"',
        'test "$EVIDENCE_EXECUTION_LOCATION" != "local-workstation"',
        'test "$EVIDENCE_RUNNER_ID" != "local-gfx1030"',
        "test -c /dev/kfd",
        "test -c /dev/dri/renderD128",
        "grep -q 'Name:[[:space:]]*gfx1100'",
        "trusted gfx1030 envelope file hash mismatch",
        "trusted envelope source SHA mismatch",
        "accepted wheel size mismatch",
        "accepted wheel hash mismatch",
        'cp -- "$CONTROL_WHEEL" "$SOURCE_WHEEL"',
        'r"sha256:[0-9a-f]{64}"',
        "--expected-architecture gfx1100",
        '--artifact-prefix "$RUN_ARTIFACT_PREFIX"',
        "--independent-from-local-gfx1030",
        '--export-evidence "${RUN_ARTIFACT_PREFIX}_evidence.canonical.json"',
        '"promotion_eligible": False',
        '"cpu_fallback_zero_not_attested"',
        '"terminal_resultir_diagnosticir_parity_not_bound"',
        '"end_to_end_performance_sweep_not_bound"',
        '"trusted_hardware_identity_receipt_not_bound"',
        "if: success()",
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ):
        assert required in raw
    assert "if: always()" not in raw
    assert (
        "RUN_ARTIFACT_PREFIX: g1_mgt_gfx1100_${{ github.run_id }}_${{ github.run_attempt }}"
        in raw
    )


def test_gfx1100_trusted_hash_constants_match_control_evidence() -> None:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    env = payload["env"]
    envelope_path = (
        ROOT / "implementation/phase1/release_evidence/productization/"
        "g1_mgt_gfx1030_hardware_envelope.json"
    )
    envelope_raw = envelope_path.read_bytes()
    envelope = json.loads(envelope_raw)
    assert (
        "sha256:" + hashlib.sha256(envelope_raw).hexdigest()
        == env["EXPECTED_GFX1030_ENVELOPE_FILE_SHA256"]
    )
    assert envelope["receipt_hash"] == env["EXPECTED_GFX1030_ENVELOPE_RECEIPT_HASH"]
    assert (
        envelope["evidence_payload"]["source"]["repository_commit_sha"]
        == env["EXPECTED_SOURCE_SHA"]
    )
    wheel = ROOT / "dist/structural_analysis-0.3.0-py3-none-any.whl"
    wheel_bytes = wheel.read_bytes()
    expected_size = int(env["EXPECTED_WHEEL_SIZE_BYTES"])
    if wheel_bytes.startswith(LFS_POINTER_VERSION.encode("ascii")):
        pointer = dict(
            line.split(" ", 1) for line in wheel_bytes.decode("ascii").splitlines()[1:]
        )
        assert pointer == {
            "oid": env["EXPECTED_WHEEL_SHA256"],
            "size": str(expected_size),
        }
    else:
        assert len(wheel_bytes) == expected_size
        assert (
            "sha256:" + hashlib.sha256(wheel_bytes).hexdigest()
            == env["EXPECTED_WHEEL_SHA256"]
        )
    assert "dist/structural_analysis-0.3.0-py3-none-any.whl filter=lfs" in (
        ROOT / ".gitattributes"
    ).read_text(encoding="utf-8")
    assert (
        subprocess.run(
            ["git", "check-ignore", "-q", str(wheel.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
        ).returncode
        == 1
    )
    assert (
        subprocess.check_output(
            ["git", "check-attr", "filter", "--", str(wheel.relative_to(ROOT))],
            cwd=ROOT,
            text=True,
        )
        .strip()
        .endswith(": lfs")
    )
