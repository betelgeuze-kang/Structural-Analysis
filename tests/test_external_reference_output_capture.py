"""Output capture contracts independent of materialized external receipts."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_capture_receipt_runner",
    ROOT / "scripts/run_external_code_to_code_technical_receipt.py",
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


@pytest.mark.parametrize("failure", [None, "exit", "json", "version"])
def test_raw_capture_keeps_opensees_output_before_validation(tmp_path, monkeypatch, failure):
    payload = {"runtime_version": module.OPENSEES_RUNTIME_VERSION}
    if failure == "version":
        payload["runtime_version"] = "invalid"
    stdout = "CODE_TO_CODE_JSON=" + ("{" if failure == "json" else json.dumps(payload)) + "\n"
    completed = subprocess.CompletedProcess([], 1 if failure == "exit" else 0, stdout, "warning Ω\n")
    monkeypatch.setattr(module, "execute_pinned_opensees", lambda **kwargs: (completed, {"sealed": True}))
    output = tmp_path / "capture"
    kwargs = dict(python_executable=Path(sys.executable), python_path=tmp_path, wheel_paths=[], raw_output_dir=output)
    if failure:
        with pytest.raises(module.ExternalCodeToCodeReceiptError):
            module._run_opensees(**kwargs)
    else:
        _, receipt = module._run_opensees(**kwargs)
        assert receipt["stdout_sha256"] == module._file_hash(output / "stdout.txt")
        assert receipt["stderr_sha256"] == module._file_hash(output / "stderr.txt")
        assert receipt["driver_sha256"] == module._file_hash(output / "driver.py")
    assert (output / "stdout.txt").read_bytes() == stdout.encode()
    assert (output / "stderr.txt").read_text() == completed.stderr
    assert json.loads((output / "execution.json").read_text())["return_code"] == completed.returncode
    monkeypatch.setattr(module, "execute_pinned_opensees", lambda **kwargs: pytest.fail("must reject existing capture before execution"))
    with pytest.raises(FileExistsError):
        module._run_opensees(**kwargs)


@pytest.mark.parametrize("mode", ["--check", "--refresh-product-replay"])
def test_raw_capture_rejects_nonexecution_modes(tmp_path, mode):
    output = tmp_path / "capture"
    with pytest.raises(SystemExit) as exc:
        module.main([mode, "--raw-output-dir", str(output)])
    assert exc.value.code == 2
    assert not output.exists()


def test_raw_capture_builder_routes_both_engines_and_preserves_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_external_asset_rows", lambda assets: [])
    license_path = tmp_path / "license.txt"
    license_path.write_text("Commercial redistribution License: GPL-2")
    output = tmp_path / "capture"
    calls = []
    def opensees(**kwargs):
        calls.append(kwargs["raw_output_dir"])
        kwargs["raw_output_dir"].mkdir()
        (kwargs["raw_output_dir"] / "stdout.txt").write_text("preserved")
        return {}, {}
    def calculix(**kwargs):
        calls.append(kwargs["raw_output_dir"])
        raise module.ExternalCodeToCodeReceiptError("intentional failure")
    monkeypatch.setattr(module, "_run_opensees", opensees)
    monkeypatch.setattr(module, "_run_calculix", calculix)
    kwargs = dict(repo_root=ROOT, python_executable=Path(sys.executable), opensees_python_path=tmp_path,
                  opensees_license_path=license_path, calculix_binary=tmp_path / "ccx",
                  calculix_library_dir=tmp_path, calculix_license_path=license_path,
                  external_assets=[], raw_output_dir=output)
    with pytest.raises(module.ExternalCodeToCodeReceiptError, match="intentional failure"):
        module.build_external_code_to_code_technical_receipt(**kwargs)
    assert calls == [output / "opensees", output / "calculix"]
    assert (output / "opensees/stdout.txt").read_text() == "preserved"
    with pytest.raises(FileExistsError):
        module.build_external_code_to_code_technical_receipt(**kwargs)
    assert len(calls) == 2


def test_raw_capture_cli_forwards_fresh_output_directory(tmp_path, monkeypatch):
    seen = {}
    def build(**kwargs):
        seen.update(kwargs)
        return {"status": "partial", "technical_contract_pass": False, "verification_hierarchy_credit": False}
    monkeypatch.setattr(module, "build_external_code_to_code_technical_receipt", build)
    output = tmp_path / "raw"
    args = ["--out", str(tmp_path / "receipt.json"), "--raw-output-dir", str(output)]
    for flag in ("--opensees-python-path", "--opensees-license", "--calculix-binary", "--calculix-library-dir", "--calculix-license"):
        args.extend([flag, str(tmp_path)])
    assert module.main(args) == 0
    assert seen["raw_output_dir"] == output.resolve()
    assert json.loads((tmp_path / "receipt.json").read_text())["technical_contract_pass"] is False


@pytest.mark.parametrize("failure", [None, "after_output", "before_output"])
def test_clean_runner_retains_distinct_attempts_and_failure_inventory(tmp_path, monkeypatch, failure):
    spec = importlib.util.spec_from_file_location(
        "clean_runner_capture_contract",
        ROOT / "benchmarks/clean-runners/opensees-calculix/run_clean_runner.py",
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    attempts = []

    def execute(command, *, cwd, env):
        assert cwd == ROOT and env == {"PYTHONPATH": str(ROOT / "src")}
        assert command[:2] == ["python", "receipt.py"]
        capture = Path(command[command.index("--raw-output-dir") + 1])
        assert not capture.exists()
        attempts.append(capture.parent)
        if failure == "before_output":
            raise runner.CleanRunnerError("reference rejected")
        capture.mkdir()
        (capture / "stderr.txt").write_text("retained warning Ω\n", encoding="utf-8")
        if failure:
            raise runner.CleanRunnerError("reference rejected")

    monkeypatch.setattr(runner, "_run", execute)
    for _ in range(2):
        kwargs = dict(output_dir=tmp_path, cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")})
        if failure:
            with pytest.raises(runner.CleanRunnerError, match="reference rejected"):
                runner._run_code_with_capture(["python", "receipt.py"], **kwargs)
        else:
            runner._run_code_with_capture(["python", "receipt.py"], **kwargs)
    assert len(set(attempts)) == 2
    for attempt in attempts:
        inventory = json.loads((attempt / "inventory.json").read_text())
        assert inventory["receipt_command_completed"] is (failure is None)
        assert inventory["signed_summary_member"] is False
        assert inventory["qualification_claim"] is False
        if failure == "before_output":
            assert inventory["files"] == []
            continue
        assert inventory["files"] == [{
            "path": "raw/stderr.txt",
            "byte_length": len("retained warning Ω\n".encode()),
            "sha256": runner._file_hash(attempt / "raw/stderr.txt"),
        }]
