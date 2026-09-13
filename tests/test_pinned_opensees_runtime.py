"""Execution-origin contracts; tiny Python wheels are not physical evidence."""

from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from typing import Any
import zipfile

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pinned_opensees_runtime as runtime  # noqa: E402


@pytest.fixture
def tiny_wheels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Exercise real isolated imports with explicitly synthetic file pins."""
    files = {
        "openseespy/__init__.py": b"",
        "openseespy/opensees/__init__.py": b"from openseespylinux.opensees import *\n",
        "openseespylinux/__init__.py": b"",
        "openseespylinux/opensees.py": b"def version(): return '3.7.1'\n",
    }
    packages = tmp_path / "packages"
    wheels = []
    pins = {}
    members = {}
    for package in ("openseespy", "openseespylinux"):
        wheel = tmp_path / (package + ".whl")
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, data in files.items():
                if name.startswith(package + "/"):
                    archive.writestr(name, data)
                    path = packages / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    members[name] = {
                        "bytes": len(data),
                        "sha256": runtime._hash_bytes(data),
                        "wheel": wheel.name,
                    }
        pins[wheel.name] = runtime._hash_file(wheel)
        wheels.append(wheel)
    manifest = tmp_path / "members.json"
    manifest.write_text(json.dumps(members))
    monkeypatch.setattr(runtime, "WHEEL_HASHES", pins)
    monkeypatch.setattr(runtime, "MEMBERS_PATH", manifest)
    monkeypatch.setattr(
        runtime,
        "MODULE_PATHS",
        {
            **runtime.MODULE_PATHS,
            "openseespylinux.opensees": "openseespylinux/opensees.py",
        },
    )
    return {
        "python_executable": Path(sys.executable),
        "supplied_runtime_root": packages,
        "wheels": wheels,
    }


def test_private_extraction_ignores_supplied_extras_and_cwd_imports(
    tiny_wheels: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poison = tmp_path / "poison"
    (poison / "openseespy").mkdir(parents=True)
    (poison / "openseespy/__init__.py").write_text("raise RuntimeError('wrong import')")
    (poison / "sitecustomize.py").write_text("raise RuntimeError('wrong startup')")
    monkeypatch.chdir(poison)
    monkeypatch.setenv("PYTHONPATH", str(poison))
    extra = tiny_wheels["supplied_runtime_root"] / "unrelated.py"
    extra.write_text("raise RuntimeError('supplied extra imported')")
    completed, binding = runtime.execute_pinned_opensees(
        **tiny_wheels,
        driver="import openseespy.opensees as ops\nprint(ops.version())",
    )
    assert completed.returncode == 0
    assert completed.stdout.splitlines()[0] == "3.7.1"
    assert binding == runtime.expected_binding()
    assert not list(tiny_wheels["supplied_runtime_root"].rglob("*.pyc"))


@pytest.mark.parametrize("change", ["member", "wheel", "duplicate", "symlink"])
def test_invalid_runtime_rejects_before_child_launch(
    tiny_wheels: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    path = tiny_wheels["supplied_runtime_root"] / "openseespylinux/opensees.py"
    if change == "member":
        path.write_text("def version(): return '3.7.1'\n# changed\n")
    elif change == "wheel":
        tiny_wheels["wheels"][0].write_bytes(b"not the pinned wheel")
    elif change == "duplicate":
        tiny_wheels["wheels"].append(tiny_wheels["wheels"][0])
    else:
        target = path.with_name("original.py")
        path.rename(target)
        path.symlink_to(target)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("invalid reference must not launch a child")

    monkeypatch.setattr(runtime.subprocess, "run", forbidden)
    with pytest.raises(runtime.PinnedOpenSeesRuntimeError) as caught:
        runtime.execute_pinned_opensees(**tiny_wheels, driver="raise AssertionError")
    assert caught.value.completed is None


@pytest.mark.parametrize(
    "driver",
    [
        "raise RuntimeError('failed driver')",
        "import openseespy.opensees as ops\nops.__file__ = '/elsewhere/module.py'",
        "import openseespy.opensees as ops\nfrom pathlib import Path\nPath(ops.__file__).write_text('changed')",
        "print('OPENSEES_WHEEL_BINDING={}')",
    ],
)
def test_child_failure_and_after_execution_drift_never_produce_binding(
    tiny_wheels: dict[str, Any],
    driver: str,
) -> None:
    with pytest.raises(
        runtime.PinnedOpenSeesRuntimeError, match="opensees_bound_execution_failed"
    ) as caught:
        runtime.execute_pinned_opensees(**tiny_wheels, driver=driver)
    assert caught.value.completed is not None
    assert isinstance(caught.value.completed.stderr, str)


@pytest.mark.parametrize(
    "field",
    [
        "member_manifest_hash",
        "member_count",
        "module_origins",
        "wheel_hashes",
        "isolated_interpreter",
        "private_wheel_extraction",
        "members_verified_before_and_after",
    ],
)
def test_rehashed_binding_tampering_is_rejected(field: str) -> None:
    binding = deepcopy(runtime.expected_binding())
    binding[field] = None
    binding["binding_hash"] = runtime._hash_value(
        {k: v for k, v in binding.items() if k != "binding_hash"}
    )
    with pytest.raises(runtime.PinnedOpenSeesRuntimeError):
        runtime.validate_binding(binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("isolated_interpreter", 1),
        ("private_wheel_extraction", 1),
        ("members_verified_before_and_after", 1),
        ("member_count", 24.0),
    ],
)
def test_binding_does_not_use_python_bool_numeric_equality(
    field: str, value: Any
) -> None:
    binding = runtime.expected_binding()
    binding[field] = value
    with pytest.raises(runtime.PinnedOpenSeesRuntimeError):
        runtime.validate_binding(binding)


@pytest.mark.parametrize(
    "schema",
    [
        "external_code_to_code_technical_receipt_v1.schema.json",
        "external_modal_buckling_technical_receipt_v1.schema.json",
    ],
)
def test_receipt_schema_has_exact_binding_and_keeps_historical_outputs(
    schema: str,
) -> None:
    document = json.loads(
        (ROOT / "src/structural_analysis/schemas" / schema).read_bytes()
    )
    validator = Draft202012Validator(document)
    validator.check_schema(document)
    bound = document["$defs"]["openseesOutputs"]["properties"]["runtime_binding"]
    assert bound["const"] == runtime.expected_binding()
    assert "runtime_binding" not in document["$defs"]["openseesOutputs"]["required"]


@pytest.mark.parametrize("kind", ["code", "modal"])
def test_actual_receipt_runner_uses_bound_execution(
    tiny_wheels: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    module = importlib.import_module(
        "run_external_code_to_code_technical_receipt"
        if kind == "code"
        else "run_external_modal_buckling_technical_receipt"
    )
    if kind == "code":
        driver = "import json\nprint('CODE_TO_CODE_JSON='+json.dumps({'runtime_version':'3.7.1'}))"
        monkeypatch.setattr(module, "OPENSEES_DRIVER", driver)
        fn = module._run_opensees
    else:
        driver = "import json\nprint('MODAL_BUCKLING_JSON='+json.dumps({'runtime_version':'3.7.1','eigenvalues':[1.,2.],'mode_matrix':[[1.,0.],[0.,1.]]}))"
        monkeypatch.setattr(module, "OPENSEES_MODAL_DRIVER", driver)
        fn = module._run_opensees_modal
    payload, outputs = fn(
        python_executable=tiny_wheels["python_executable"],
        python_path=tiny_wheels["supplied_runtime_root"],
        wheel_paths=tiny_wheels["wheels"],
    )
    assert payload["runtime_version"] == "3.7.1"
    assert outputs["runtime_binding"] == runtime.expected_binding()


@pytest.mark.parametrize("kind", ["code", "modal"])
def test_new_fresh_receipt_cannot_omit_binding(kind: str) -> None:
    module = importlib.import_module(
        "run_external_code_to_code_technical_receipt"
        if kind == "code"
        else "run_external_modal_buckling_technical_receipt"
    )
    filename = (
        "external_code_to_code_technical_execution_receipt.json"
        if kind == "code"
        else "external_modal_buckling_technical_execution_receipt.json"
    )
    path = ROOT / "implementation/phase1/release_evidence/productization" / filename
    payload = json.loads(path.read_bytes())
    checksums = payload["internal_source"]["input_checksums"]
    checksums["scripts/pinned_opensees_runtime.py"] = "sha256:" + "1" * 64
    payload["internal_source"]["source_set_hash"] = module._hash_value(checksums)
    payload["runtimes"]["opensees"]["execution_outputs"].pop("runtime_binding", None)
    payload["replay_provenance"].update(
        {
            "external_runtime_executed_in_this_generation": True,
            "external_execution_reused": False,
            "reuse_reason": None,
            "external_execution_source_commit_sha": payload["source_commit_sha"],
        }
    )
    payload["artifact_hash"] = module._artifact_hash(payload)
    fn = (
        module.validate_external_code_to_code_technical_receipt
        if kind == "code"
        else module.validate_external_modal_buckling_technical_receipt
    )
    with pytest.raises(ValueError, match="opensees_current_execution_binding_missing"):
        fn(payload, repo_root=ROOT, require_current_sources=False)


def test_wheel_pins_and_source_manifests_cover_runtime_binding() -> None:
    code = importlib.import_module("run_external_code_to_code_technical_receipt")
    modal = importlib.import_module("run_external_modal_buckling_technical_receipt")
    assert {
        name: row["sha256"]
        for name, row in code.EXTERNAL_ASSET_POLICY.items()
        if name.endswith(".whl")
    } == runtime.WHEEL_HASHES
    for module in (code, modal):
        checksums = module._source_checksums(ROOT)
        for path in (
            "scripts/pinned_opensees_runtime.py",
            "scripts/pinned_opensees_wheel_members.json",
        ):
            assert checksums[path] == runtime._hash_file(ROOT / path)
