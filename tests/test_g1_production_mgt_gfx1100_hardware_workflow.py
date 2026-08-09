from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/g1-production-mgt-gfx1100-hardware.yml"
LFS_POINTER_VERSION = "version https://git-lfs.github.com/spec/v1"
SOURCE_BOUND_RUFF_EXCEPTIONS = {
    "scripts/run_g1_hip_fgmres_performance_sweep.py": ["E701", "E702", "F401"],
    "scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py": ["F401"],
    "scripts/run_g1_mgt_accepted_state_preconditioned_jvp_parity.py": [
        "E701",
        "E702",
    ],
    "scripts/run_g1_mgt_device_fgmres.py": ["E701", "E702"],
    "scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py": ["E701", "E702"],
    "scripts/run_g1_stateful_steel_hip_lifecycle.py": ["E701", "E702", "F841"],
    "tests/test_g1_hip_fgmres_performance_sweep.py": ["E702"],
    "tests/test_run_g1_mgt_accepted_state_preconditioned_jvp_parity.py": [
        "E702"
    ],
    "tests/test_run_g1_mgt_device_fgmres.py": ["E402"],
    "tests/test_run_g1_mgt_single_lifecycle_preconditioned_jvp.py": ["E702"],
    "tests/test_run_g1_stateful_steel_hip_lifecycle.py": ["E402"],
}
E701_E702_SOURCE_BOUND_PATHS = {
    "scripts/run_g1_hip_fgmres_performance_sweep.py",
    "scripts/run_g1_mgt_accepted_state_preconditioned_jvp_parity.py",
    "scripts/run_g1_mgt_device_fgmres.py",
    "scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py",
    "scripts/run_g1_stateful_steel_hip_lifecycle.py",
}


def _scalar(value: str) -> Any:
    value = value.strip()
    if value == "{}":
        return {}
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        return [_scalar(item) for item in value[1:-1].split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _direct_mapping(lines: list[str], *, indent: int) -> dict[str, Any]:
    prefix = " " * indent
    mapping: dict[str, Any] = {}
    for line in lines:
        if not line.startswith(prefix) or line.startswith(prefix + " "):
            continue
        key, separator, value = line[len(prefix) :].partition(":")
        if separator and value.strip():
            mapping[key] = _scalar(value)
        elif separator:
            mapping[key] = {}
    return mapping


def _block(lines: list[str], header: str, *, indent: int) -> list[str]:
    header_line = " " * indent + header + ":"
    start = lines.index(header_line) + 1
    result: list[str] = []
    for line in lines[start:]:
        if line and len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line)
    return result


def _checkout_steps(job_lines: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, line in enumerate(job_lines):
        if not line.startswith("        uses: actions/checkout@"):
            continue
        with_lines: list[str] = []
        for candidate in job_lines[index + 1 :]:
            if candidate.startswith("      - name:"):
                break
            if candidate.startswith("          "):
                with_lines.append(candidate)
        steps.append(
            {
                "uses": line.split(":", 1)[1].strip(),
                "with": _direct_mapping(with_lines, indent=10),
            }
        )
    return steps


def _load_workflow_contract() -> dict[str, Any]:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    trigger = _direct_mapping(_block(lines, "on", indent=0), indent=2)
    env = _direct_mapping(_block(lines, "env", indent=0), indent=2)
    jobs = _block(lines, "jobs", indent=0)
    job_lines = _block(jobs, "production-gfx1100", indent=2)
    job = _direct_mapping(job_lines, indent=4)
    job["steps"] = _checkout_steps(job_lines)
    return {
        "on": trigger,
        "env": env,
        "jobs": {"production-gfx1100": job},
    }


def test_gfx1100_workflow_is_manual_and_dedicated() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    payload = _load_workflow_contract()
    trigger = payload["on"]
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
    payload = _load_workflow_contract()
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


def test_source_bound_g1_ruff_exceptions_are_exact_paths() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = pyproject.split("[tool.ruff.lint.per-file-ignores]", 1)[1].split(
        "[tool.pytest.ini_options]", 1
    )[0]
    configured = {}
    configured_paths = []
    for line in section.splitlines():
        if not line.startswith('"'):
            continue
        path = line.split('"', 2)[1]
        configured_paths.append(path)
        if path in SOURCE_BOUND_RUFF_EXCEPTIONS:
            configured[path] = json.loads(line.split("=", 1)[1])
    assert configured == SOURCE_BOUND_RUFF_EXCEPTIONS
    assert {
        path for path, codes in configured.items() if {"E701", "E702"} <= set(codes)
    } == E701_E702_SOURCE_BOUND_PATHS
    assert not any(
        wildcard in path for path in configured_paths for wildcard in ("*", "?", "[")
    )
    assert "byte-bound to hardware/source evidence" in section
