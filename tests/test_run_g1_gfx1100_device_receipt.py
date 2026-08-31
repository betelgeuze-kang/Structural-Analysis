from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_g1_gfx1100_device_receipt.py"
spec = importlib.util.spec_from_file_location("run_g1_gfx1100_device_receipt", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

HEAD = "a" * 40
PROTECTED_GFX1030 = (
    ROOT / "implementation/phase1/release_evidence/productization/"
    "engine_v2_hip_fgmres_gfx1030_device_receipt.json"
)


def _wheel(path: Path) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "example_project-2.3.4.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: example-project\nVersion: 2.3.4\n",
        )
    return path.read_bytes()


def _legacy_gfx1100_receipt(
    *,
    wheel_path: Path,
    operator_context: dict,
) -> dict:
    receipt = json.loads(PROTECTED_GFX1030.read_text(encoding="utf-8"))
    evidence = receipt["evidence_payload"]
    evidence["operator_context"] = deepcopy(operator_context)
    evidence["wheel"] = module.legacy_runner.wheel_identity(wheel_path)
    hardware = evidence["hardware_execution"]
    hardware["evidence_origin"] = "direct_device_runner"
    hardware["upstream_receipt_hash"] = None
    hardware["gcn_arch_name"] = "gfx1100"
    hardware["runtime_output"]["gcn_arch_name"] = "gfx1100"
    evidence["recurrence_comparison"]["gcn_arch_name"] = "gfx1100"
    return receipt


def _configure_clean_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "git_head", lambda _root: HEAD)
    monkeypatch.setattr(
        module.legacy_runner.local_runner,
        "_worktree_clean",
        lambda _root: True,
    )


def _generate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mutate_original: bool = False,
) -> tuple[dict, Path, bytes, dict]:
    _configure_clean_checkout(monkeypatch)
    wheel_path = tmp_path / "original-candidate.whl"
    original = _wheel(wheel_path)
    observed: dict = {}

    def fake_hardware_runner(**kwargs):
        private = kwargs["wheel_path"]
        metadata = private.lstat()
        observed["private_bytes"] = private.read_bytes()
        observed["private_parent_mode"] = stat.S_IMODE(private.parent.stat().st_mode)
        observed["private_file_mode"] = stat.S_IMODE(metadata.st_mode)
        observed["private_regular"] = stat.S_ISREG(metadata.st_mode)
        observed["compile_source_sha256"] = module._sha256_bytes(kwargs["source_bytes"])
        assert observed["compile_source_sha256"] == kwargs["source_sha256"]
        if mutate_original:
            wheel_path.write_bytes(b"changed-after-one-shot-read")
        return _legacy_gfx1100_receipt(
            wheel_path=private,
            operator_context=kwargs["operator_context"],
        )

    monkeypatch.setattr(
        module,
        "_run_hardware_from_source_snapshot",
        fake_hardware_runner,
    )
    receipt = module.run_gfx1100_device_receipt(
        repo_root=ROOT,
        wheel_path=wheel_path,
        expected_source_sha=HEAD,
        operator_context={
            "organization_id": "independent-lab-a",
            "runner_id": "external-gfx1100::github_run_id=123::run_attempt=1",
            "execution_location": "external-lab",
            "independent_from_local_gfx1030": True,
        },
        hipcc="/opt/rocm/bin/hipcc",
        rocminfo="rocminfo",
        rocm_path="/opt/rocm",
        device_lib_path="",
    )
    return receipt, wheel_path, original, observed


def _rehash(receipt: dict, *, refresh_signature: bool = False) -> None:
    if refresh_signature:
        receipt["signature"] = module._unsigned_signature(receipt["evidence_payload"])
    receipt["receipt_hash"] = module.fgmres_recurrence_receipt_hash(receipt)


def test_dedicated_runner_uses_private_one_shot_wheel_and_keeps_false_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, wheel_path, original, observed = _generate(
        tmp_path,
        monkeypatch,
        mutate_original=True,
    )

    wheel = receipt["evidence_payload"]["wheel"]
    source = receipt["evidence_payload"]["source"]
    assert observed == {
        "private_bytes": original,
        "private_parent_mode": 0o700,
        "private_file_mode": 0o600,
        "private_regular": True,
        "compile_source_sha256": receipt["evidence_payload"]["source"][
            "input_checksums"
        ][module.legacy_runner.local_runner.SOURCE_PATH.as_posix()],
    }
    assert wheel_path.read_bytes() == b"changed-after-one-shot-read"
    assert wheel["filename"] == "original-candidate.whl"
    assert wheel["sha256"] == module._sha256_bytes(original)
    assert wheel["bound_at_execution"] is False
    assert receipt["claims"]["wheel_identity_bound_at_execution"] is False
    assert "wheel_identity_not_bound_at_execution" in receipt["blockers_remaining"]
    assert receipt["claims"]["cross_device_stage4"] is False
    assert receipt["claims"]["production_recurrence"] is False
    assert receipt["claims"]["performance"] is False
    assert source["repository_commit_sha"] == HEAD
    assert source["worktree_clean"] is True
    assert source["exact_source_commit_claim"] is True
    assert set(source["input_checksums"]) == {
        path.as_posix() for path in module.SOURCE_PATHS
    }
    assert "scripts/run_g1_gfx1100_device_receipt.py" in source["input_checksums"]
    assert "tests/test_run_g1_gfx1100_device_receipt.py" in source["input_checksums"]


def test_hardware_helper_compiles_only_captured_source_stdin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel_path = tmp_path / "candidate.whl"
    _wheel(wheel_path)
    source_bytes = b"#include <hip/hip_runtime.h>\nint main() { return 0; }\n"
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        module.legacy_runner.local_runner,
        "_resolve_hipcc",
        lambda _value: Path("/fake/hipcc"),
    )
    monkeypatch.setattr(
        module.legacy_runner.local_runner,
        "_resolve_device_lib_path",
        lambda _root, _value: Path("/fake/device-libs"),
    )
    monkeypatch.setattr(
        module.legacy_runner.local_runner,
        "_detect_architecture",
        lambda _root, _value: "gfx1100",
    )

    def fake_local_run(command, **_kwargs):
        if "--version" in command:
            return module.subprocess.CompletedProcess(
                command,
                0,
                stdout="hipcc test version\n",
                stderr="",
            )
        return module.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"gcn_arch_name": "gfx1100"}) + "\n",
            stderr="",
        )

    def fake_compile(command, **kwargs):
        captured["compile_command"] = command
        captured["compile_input"] = kwargs["input"]
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"compiled-binary")
        return module.subprocess.CompletedProcess(
            command,
            0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(module.legacy_runner.local_runner, "_run", fake_local_run)
    monkeypatch.setattr(module.subprocess, "run", fake_compile)
    monkeypatch.setattr(
        module.legacy_runner,
        "build_device_receipt_from_runtime_output",
        lambda runtime, **kwargs: {
            "runtime": runtime,
            "binary_sha256": kwargs["binary_sha256"],
        },
    )

    result = module._run_hardware_from_source_snapshot(
        repo_root=ROOT,
        wheel_path=wheel_path,
        operator_context={
            "organization_id": "lab",
            "runner_id": "runner",
            "execution_location": "location",
            "independent_from_local_gfx1030": True,
        },
        hipcc="/fake/hipcc",
        rocminfo="rocminfo",
        rocm_path="/fake/rocm",
        device_lib_path="/fake/device-libs",
        source_bytes=source_bytes,
        source_sha256=module._sha256_bytes(source_bytes),
    )

    command = captured["compile_command"]
    assert isinstance(command, list)
    assert command[command.index("-x") + 1 : command.index("-x") + 3] == ["hip", "-"]
    assert str(ROOT / module.legacy_runner.local_runner.SOURCE_PATH) not in command
    assert captured["compile_input"] == source_bytes
    assert result["runtime"]["gcn_arch_name"] == "gfx1100"


def test_public_validator_rejects_false_wheel_promotion_and_blocker_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _wheel_path, _original, _observed = _generate(tmp_path, monkeypatch)

    promoted = deepcopy(receipt)
    promoted["evidence_payload"]["wheel"]["bound_at_execution"] = True
    _rehash(promoted, refresh_signature=True)
    with pytest.raises(ValueError, match="wheel_execution_claim_invalid"):
        module.validate_gfx1100_device_receipt(promoted, ROOT, False)

    blocker_removed = deepcopy(receipt)
    blocker_removed["blockers_remaining"].remove(
        "wheel_identity_not_bound_at_execution"
    )
    _rehash(blocker_removed)
    with pytest.raises(ValueError, match="blockers_invalid"):
        module.validate_gfx1100_device_receipt(blocker_removed, ROOT, False)


def test_public_validator_requires_exact_dedicated_source_path_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _wheel_path, _original, _observed = _generate(tmp_path, monkeypatch)
    tampered = deepcopy(receipt)
    checksums = tampered["evidence_payload"]["source"]["input_checksums"]
    checksums.pop("tests/test_run_g1_gfx1100_device_receipt.py")
    tampered["evidence_payload"]["source"]["source_set_hash"] = module._source_set_hash(
        checksums
    )
    _rehash(tampered, refresh_signature=True)

    with pytest.raises(ValueError, match="source_path_set_invalid"):
        module.validate_gfx1100_device_receipt(tampered, ROOT, False)


def test_generation_fails_before_hardware_on_commit_or_cleanliness_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel_path = tmp_path / "candidate.whl"
    _wheel(wheel_path)
    called = False

    def should_not_run(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("hardware runner must not execute")

    monkeypatch.setattr(
        module,
        "_run_hardware_from_source_snapshot",
        should_not_run,
    )
    monkeypatch.setattr(module, "git_head", lambda _root: HEAD)
    monkeypatch.setattr(
        module.legacy_runner.local_runner,
        "_worktree_clean",
        lambda _root: False,
    )
    arguments = {
        "repo_root": ROOT,
        "wheel_path": wheel_path,
        "operator_context": {
            "organization_id": "lab",
            "runner_id": "runner",
            "execution_location": "location",
            "independent_from_local_gfx1030": True,
        },
        "hipcc": "hipcc",
        "rocminfo": "rocminfo",
        "rocm_path": "/opt/rocm",
        "device_lib_path": "",
    }
    with pytest.raises(ValueError, match="expected_source_sha_mismatch"):
        module.run_gfx1100_device_receipt(
            **arguments,
            expected_source_sha="b" * 40,
        )
    with pytest.raises(ValueError, match="worktree_not_clean"):
        module.run_gfx1100_device_receipt(
            **arguments,
            expected_source_sha=HEAD,
        )
    assert called is False


def test_generation_rejects_source_change_during_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_clean_checkout(monkeypatch)
    wheel_path = tmp_path / "candidate.whl"
    _wheel(wheel_path)
    current = module._current_input_snapshot(ROOT)
    changed = {**current, next(iter(current)): b"changed"}
    calls = 0

    def changing_sources(_root):
        nonlocal calls
        calls += 1
        return current if calls == 1 else changed

    monkeypatch.setattr(module, "_current_input_snapshot", changing_sources)
    monkeypatch.setattr(
        module,
        "_run_hardware_from_source_snapshot",
        lambda **kwargs: _legacy_gfx1100_receipt(
            wheel_path=kwargs["wheel_path"],
            operator_context=kwargs["operator_context"],
        ),
    )
    with pytest.raises(ValueError, match="source_changed_during_execution"):
        module.run_gfx1100_device_receipt(
            repo_root=ROOT,
            wheel_path=wheel_path,
            expected_source_sha=HEAD,
            operator_context={
                "organization_id": "lab",
                "runner_id": "runner",
                "execution_location": "location",
                "independent_from_local_gfx1030": True,
            },
            hipcc="hipcc",
            rocminfo="rocminfo",
            rocm_path="/opt/rocm",
            device_lib_path="",
        )


def test_generation_compiles_captured_bytes_when_checkout_path_changes_and_restores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_clean_checkout(monkeypatch)
    repo_root = tmp_path / "repo"
    for relative in module.SOURCE_PATHS:
        target = repo_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    compile_path = repo_root / module.legacy_runner.local_runner.SOURCE_PATH
    original_source = compile_path.read_bytes()
    wheel_path = tmp_path / "candidate.whl"
    _wheel(wheel_path)
    observed: dict[str, bytes] = {}

    def change_and_restore_checkout(**kwargs):
        compile_path.write_bytes(b"attacker-controlled-source")
        try:
            observed["compiled"] = kwargs["source_bytes"]
            assert kwargs["source_sha256"] == module._sha256_bytes(original_source)
        finally:
            compile_path.write_bytes(original_source)
        return _legacy_gfx1100_receipt(
            wheel_path=kwargs["wheel_path"],
            operator_context=kwargs["operator_context"],
        )

    monkeypatch.setattr(
        module,
        "_run_hardware_from_source_snapshot",
        change_and_restore_checkout,
    )
    receipt = module.run_gfx1100_device_receipt(
        repo_root=repo_root,
        wheel_path=wheel_path,
        expected_source_sha=HEAD,
        operator_context={
            "organization_id": "lab",
            "runner_id": "runner",
            "execution_location": "location",
            "independent_from_local_gfx1030": True,
        },
        hipcc="hipcc",
        rocminfo="rocminfo",
        rocm_path="/opt/rocm",
        device_lib_path="",
    )

    assert observed["compiled"] == original_source
    assert compile_path.read_bytes() == original_source
    assert receipt["evidence_payload"]["source"]["input_checksums"][
        module.legacy_runner.local_runner.SOURCE_PATH.as_posix()
    ] == module._sha256_bytes(original_source)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"name":1,"name":2}',
        b'{"outer":{"name":1,"\\u006eame":2}}',
    ],
)
def test_strict_json_rejects_literal_and_escaped_equivalent_duplicates(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError, match="json_duplicate_key:name"):
        module.decode_gfx1100_device_receipt_bytes(raw)


def test_atomic_outputs_reject_leaf_and_parent_symlinks(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_bytes(b"preserve")
    leaf = tmp_path / "receipt.json"
    leaf.symlink_to(victim)
    with pytest.raises(ValueError, match="receipt_output_leaf_invalid"):
        module._atomic_write_bytes(
            leaf,
            b"replacement",
            error_prefix="g1_gfx1100_receipt_output",
        )
    assert victim.read_bytes() == b"preserve"

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="signing_payload_output_parent_invalid"):
        module._atomic_write_bytes(
            linked_parent / "payload.json",
            b"payload",
            error_prefix="g1_gfx1100_signing_payload_output",
        )
    assert not (real_parent / "payload.json").exists()


def test_regular_reader_fifo_swap_is_nonblocking_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "receipt.json"
    target.write_text("{}\n", encoding="utf-8")
    real_stat = module.os.stat
    swapped = False

    def swap_after_stat(path, *args, **kwargs):
        nonlocal swapped
        result = real_stat(path, *args, **kwargs)
        if (
            path == target.name
            and kwargs.get("follow_symlinks") is False
            and not swapped
        ):
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return result

    monkeypatch.setattr(module.os, "stat", swap_after_stat)
    with pytest.raises(ValueError, match="receipt_input_identity_changed"):
        module._read_regular_bytes(
            target,
            error_prefix="g1_gfx1100_receipt_input",
            max_bytes=1024,
        )


def test_detached_ed25519_attach_and_custom_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography.hazmat.primitives")
    from cryptography.hazmat.primitives import serialization

    Ed25519PrivateKey = pytest.importorskip(
        "cryptography.hazmat.primitives.asymmetric.ed25519"
    ).Ed25519PrivateKey
    receipt, _wheel_path, _original, _observed = _generate(tmp_path, monkeypatch)
    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(module.device_evidence_bytes(receipt))
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    signed = module.attach_ed25519_signature(
        receipt,
        signature_bytes=signature,
        public_key_pem=public_pem,
        signer_id="independent-signer-a",
        repo_root=ROOT,
    )

    assert signed["signature"]["state"] == "verified"
    assert signed["claims"]["signed_receipt"] is True
    assert "device_receipt_signature_not_attached" not in signed["blockers_remaining"]
    assert "wheel_identity_not_bound_at_execution" in signed["blockers_remaining"]
    assert module.validate_gfx1100_device_receipt(signed, ROOT, True) == signed


def test_cli_generation_requires_exact_sha_and_independence(tmp_path: Path) -> None:
    wheel_path = tmp_path / "candidate.whl"
    _wheel(wheel_path)
    base = [
        "--out",
        str(tmp_path / "out.json"),
        "--wheel",
        str(wheel_path),
        "--organization-id",
        "lab",
        "--runner-id",
        "runner",
        "--execution-location",
        "location",
    ]
    with pytest.raises(SystemExit, match="2"):
        module.main(base)
    with pytest.raises(SystemExit, match="2"):
        module.main([*base, "--expected-source-sha", HEAD])


@pytest.mark.parametrize(
    "extra",
    [
        ["--expected-source-sha", HEAD],
        ["--wheel", "other.whl"],
        ["--signing-payload-out", "payload.json"],
        ["--hipcc", "/opt/rocm/bin/hipcc"],
    ],
)
def test_cli_check_rejects_every_cross_mode_selector(
    tmp_path: Path,
    extra: list[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        module.main(["--out", str(tmp_path / "receipt.json"), "--check", *extra])


def test_cli_attach_and_generation_reject_cross_mode_selectors(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        module.main(
            [
                "--out",
                str(tmp_path / "receipt.json"),
                "--attach-signature",
                str(tmp_path / "signature.bin"),
                "--public-key",
                str(tmp_path / "public.pem"),
                "--signer-id",
                "signer-a",
                "--wheel",
                str(tmp_path / "candidate.whl"),
            ]
        )
    with pytest.raises(SystemExit, match="2"):
        module.main(
            [
                "--out",
                str(tmp_path / "receipt.json"),
                "--public-key",
                str(tmp_path / "public.pem"),
            ]
        )
