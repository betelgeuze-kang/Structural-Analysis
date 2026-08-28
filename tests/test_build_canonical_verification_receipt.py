from __future__ import annotations

import base64
import csv
import io
import json
import hashlib
from pathlib import Path
import subprocess
import zipfile

from jsonschema import Draft202012Validator
import pytest

from scripts import build_canonical_verification_receipt as module
from scripts import check_generated_artifact_dag as dag_module


ROOT = Path(__file__).resolve().parents[1]


def test_git_commands_scope_safe_directory_to_resolved_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        observed["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._git_source_sha(tmp_path) == "a" * 40
    assert observed["command"] == [
        "git",
        "-c",
        f"safe.directory={tmp_path.resolve()}",
        "rev-parse",
        "HEAD",
    ]
    assert observed["cwd"] == tmp_path


def _linear_algebra_runtime(
    locked: dict[str, dict[str, str]],
) -> dict[str, object]:
    raw_roles = {
        role: {
            "name": "scipy-openblas",
            "version": "0.3.29",
            "found": True,
            "detection method": "pkgconfig",
            "openblas configuration": f"OpenBLAS Haswell {role}",
            "include directory": "/usr/local/include",
        }
        for role in ("blas", "lapack")
    }
    roles = {
        role: module._linear_algebra_role_identity(raw_roles[role])
        for role in ("blas", "lapack")
    }
    library_specs = (
        (
            "numpy",
            "libscipy_openblas64_numpy.so",
            "numpy.libs/libscipy_openblas64_numpy.so",
            "1" * 64,
        ),
        (
            "scipy",
            "libscipy_openblas_scipy.so",
            "scipy.libs/libscipy_openblas_scipy.so",
            "2" * 64,
        ),
    )
    loaded_libraries = []
    raw_libraries = []
    for distribution, filename, member, digest in library_specs:
        path = f"/usr/local/lib/python3.12/site-packages/{distribution}.libs/{filename}"
        wheel_filename = (
            f"{distribution}-{locked[distribution]['version']}-"
            "cp312-cp312-manylinux2014_x86_64.whl"
        )
        raw_libraries.append({"path": path, "sha256": digest})
        loaded_libraries.append(
            {
                "path": path,
                "filename": filename,
                "sha256": "sha256:" + digest,
                "distribution": distribution,
                "member": member,
                "wheel_filename": wheel_filename,
                "wheel_sha256": ("sha256:" + locked[distribution]["wheel_sha256"]),
            }
        )
    libraries = [
        {key: row[key] for key in module.LINEAR_ALGEBRA_LIBRARY_KEYS}
        for row in sorted(
            loaded_libraries,
            key=lambda row: (
                row["distribution"],
                row["filename"],
                row["sha256"],
            ),
        )
    ]
    stable_projection = {
        "provider_family": "openblas",
        "openblas_coretype": "Haswell",
        "roles": roles,
        "libraries": libraries,
    }
    return {
        "blas": raw_roles["blas"],
        "lapack": raw_roles["lapack"],
        "linear_algebra_shared_libraries": raw_libraries,
        "linear_algebra_identity": {
            **stable_projection,
            "fingerprint_sha256": module._canonical_hash(stable_projection),
            "loaded_libraries": loaded_libraries,
            "wheel_membership_verified": True,
        },
    }


def test_checked_in_environment_is_digest_and_hash_pinned() -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])

    assert config["container"]["image"] == "docker.io/library/python:3.12.11-bookworm"
    assert config["container"]["digest"] == (
        "sha256:47d28e7d429679c31c3ea60e90857c54c7967084685e2ee287935116e5a79b92"
    )
    assert config["python"] == {
        "implementation": "CPython",
        "version": "3.12.11",
        "abi": "cp312",
    }
    assert locked["numpy"]["version"] == "2.2.6"
    assert locked["scipy"]["version"] == "1.15.3"
    assert locked["pip"]["version"] == config["build"]["frontend_version"]
    assert all(len(row["wheel_sha256"]) == 64 for row in locked.values())
    assert config["project_wheel"]["contract_schema_version"] == (
        "canonical-project-wheel-contract.v1"
    )
    assert config["linear_algebra"] == {
        "provider_family": "openblas",
        "wheel_bound_distributions": ["numpy", "scipy"],
        "identity": ("loaded-shared-library-sha256-bound-to-exact-locked-wheel-member"),
    }


def test_lock_rejects_unhashed_or_ranged_dependency(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("numpy>=2\n", encoding="utf-8")

    with pytest.raises(module.CanonicalEnvironmentError, match="not exactly hashed"):
        module.load_lock(lock)


def test_receipt_schema_keeps_legacy_v1_readable_but_strengthens_new_profile() -> None:
    schema = json.loads(
        (ROOT / "canonical/canonical-verification-receipt.v1.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    legacy = {
        "schema_version": "canonical-verification-receipt.v1",
        "source_commit_sha": "a" * 40,
        "container": {
            "image": "example.invalid/python",
            "digest": "sha256:" + "0" * 64,
            "platform": "linux/amd64",
        },
        "runtime": {
            "python": {},
            "packages": {"numpy": {}, "scipy": {}},
            "os": {},
            "libc": {},
            "blas": {},
            "lapack": {},
            "linear_algebra_shared_libraries": [],
            "thread_limits": {},
            "locale": {},
            "timezone": "UTC",
            "python_hash_seed": "0",
        },
        "contract_pass": False,
        "violations": ["legacy_receipt"],
    }

    validator.validate(legacy)
    legacy_with_unprofiled_identity = json.loads(json.dumps(legacy))
    legacy_with_unprofiled_identity["runtime"]["linear_algebra_identity"] = {
        "legacy_observation": True
    }
    validator.validate(legacy_with_unprofiled_identity)
    strengthened = {**legacy, "contract_profile": module.INSTALLED_WHEEL_PROFILE}
    errors = sorted(validator.iter_errors(strengthened), key=lambda error: error.path)
    assert errors
    assert any("project_wheel" in error.message for error in errors)

    unknown_profile = {**legacy, "contract_profile": "unbounded-profile.v1"}
    errors = list(validator.iter_errors(unknown_profile))
    assert errors
    assert any("p0-canonical-installed-wheel.v1" in error.message for error in errors)


def test_receipt_schema_requires_strict_new_profile_linear_algebra_items() -> None:
    schema = json.loads(
        (ROOT / "canonical/canonical-verification-receipt.v1.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    locked = module.load_lock(
        ROOT / "canonical/requirements-cp312-manylinux2014-x86_64.lock"
    )
    receipt = {
        "schema_version": "canonical-verification-receipt.v1",
        "contract_profile": module.INSTALLED_WHEEL_PROFILE,
        "source_commit_sha": "a" * 40,
        "source_checkout_head_sha": "a" * 40,
        "source_date_epoch": 123,
        "container": {
            "image": "example.invalid/python",
            "digest": "sha256:" + "0" * 64,
            "platform": "linux/amd64",
        },
        "project_wheel": {
            key: {}
            for key in (
                "schema_version",
                "source_commit_sha",
                "source_date_epoch",
                "build",
                "dependency_wheelhouse",
                "wheel",
                "installed_replay",
                "contract_pass",
                "violations",
            )
        },
        "runtime": {
            "python": {},
            "packages": {"numpy": {}, "scipy": {}},
            "os": {},
            "libc": {},
            **_linear_algebra_runtime(locked),
            "thread_limits": {},
            "locale": {},
            "timezone": "UTC",
            "python_hash_seed": "0",
        },
        "contract_pass": True,
        "violations": [],
    }

    assert list(validator.iter_errors(receipt)) == []

    unexpected_item_field = json.loads(json.dumps(receipt))
    unexpected_item_field["runtime"]["linear_algebra_identity"]["loaded_libraries"][0][
        "unbound_claim"
    ] = True
    assert list(validator.iter_errors(unexpected_item_field))

    malformed_raw_hash = json.loads(json.dumps(receipt))
    malformed_raw_hash["runtime"]["linear_algebra_shared_libraries"][0]["sha256"] = (
        "sha256:" + "1" * 64
    )
    assert list(validator.iter_errors(malformed_raw_hash))

    for mutation in ("raw_path", "loaded_path", "member", "wheel_filename"):
        backslash = json.loads(json.dumps(receipt))
        runtime = backslash["runtime"]
        identity = runtime["linear_algebra_identity"]
        if mutation == "raw_path":
            runtime["linear_algebra_shared_libraries"][0]["path"] = (
                "/site-packages\\numpy.libs/libopenblas.so"
            )
        elif mutation == "loaded_path":
            identity["loaded_libraries"][0]["path"] = (
                "/site-packages\\numpy.libs/libopenblas.so"
            )
        elif mutation == "member":
            identity["loaded_libraries"][0]["member"] = "numpy.libs\\libopenblas.so"
        else:
            identity["loaded_libraries"][0]["wheel_filename"] = "numpy-2.2.6\\cp312.whl"
        assert list(validator.iter_errors(backslash)), mutation


@pytest.mark.parametrize(
    ("mutation", "expected_violation"),
    [
        (
            "stable_projection",
            "canonical_receipt_linear_algebra_libraries_projection_mismatch",
        ),
        ("runtime_hash", "canonical_receipt_linear_algebra_runtime_binding_mismatch"),
        (
            "missing_numpy",
            "canonical_receipt_linear_algebra_distribution_coverage_mismatch",
        ),
        (
            "wheel_hash",
            "canonical_receipt_linear_algebra_locked_wheel_sha256_mismatch:numpy",
        ),
        ("path", "canonical_receipt_linear_algebra_path_filename_mismatch:0"),
        (
            "backslash_path",
            "canonical_receipt_linear_algebra_path_filename_mismatch:0",
        ),
        (
            "backslash_member",
            "canonical_receipt_linear_algebra_member_filename_mismatch:0",
        ),
        (
            "backslash_wheel",
            "canonical_receipt_linear_algebra_locked_wheel_filename_mismatch:numpy",
        ),
        (
            "runtime_role",
            "canonical_receipt_linear_algebra_role_runtime_mismatch:blas",
        ),
        (
            "provider_values",
            "canonical_receipt_linear_algebra_role_provider_mismatch:blas",
        ),
        ("provider", "canonical_receipt_linear_algebra_provider_mismatch"),
        ("coretype", "canonical_receipt_linear_algebra_coretype_mismatch"),
        ("fingerprint", "canonical_receipt_linear_algebra_fingerprint_mismatch"),
    ],
)
def test_persisted_linear_algebra_identity_rejects_disconnected_claims(
    mutation: str,
    expected_violation: str,
) -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])
    runtime = _linear_algebra_runtime(locked)
    identity = runtime["linear_algebra_identity"]

    if mutation == "stable_projection":
        identity["libraries"][0]["sha256"] = "sha256:" + "3" * 64
    elif mutation == "runtime_hash":
        runtime["linear_algebra_shared_libraries"][0]["sha256"] = "3" * 64
    elif mutation == "missing_numpy":
        runtime["linear_algebra_shared_libraries"] = runtime[
            "linear_algebra_shared_libraries"
        ][1:]
        identity["loaded_libraries"] = identity["loaded_libraries"][1:]
        identity["libraries"] = identity["libraries"][1:]
    elif mutation == "wheel_hash":
        identity["loaded_libraries"][0]["wheel_sha256"] = "sha256:" + "3" * 64
        identity["libraries"][0]["wheel_sha256"] = "sha256:" + "3" * 64
    elif mutation in {"path", "backslash_path"}:
        path = (
            "/site-packages/numpy.libs/renamed.so"
            if mutation == "path"
            else "/site-packages\\numpy.libs/libscipy_openblas64_numpy.so"
        )
        runtime["linear_algebra_shared_libraries"][0]["path"] = path
        identity["loaded_libraries"][0]["path"] = path
    elif mutation == "backslash_member":
        member = "numpy.libs\\libscipy_openblas64_numpy.so"
        identity["loaded_libraries"][0]["member"] = member
        identity["libraries"][0]["member"] = member
    elif mutation == "backslash_wheel":
        wheel = "numpy-2.2.6\\cp312-cp312-manylinux2014_x86_64.whl"
        identity["loaded_libraries"][0]["wheel_filename"] = wheel
        identity["libraries"][0]["wheel_filename"] = wheel
    elif mutation == "runtime_role":
        runtime["blas"]["version"] = "tampered"
    elif mutation == "provider_values":
        for role in (runtime["blas"], identity["roles"]["blas"]):
            role["name"] = "generic-blas"
            role["openblas configuration"] = "unknown"
    elif mutation == "provider":
        identity["provider_family"] = "mkl"
    elif mutation == "coretype":
        identity["openblas_coretype"] = "Zen"

    projection = {
        key: identity[key]
        for key in ("provider_family", "openblas_coretype", "roles", "libraries")
    }
    identity["fingerprint_sha256"] = module._canonical_hash(projection)
    if mutation == "fingerprint":
        identity["fingerprint_sha256"] = "sha256:" + "3" * 64

    assert expected_violation in module._validate_persisted_linear_algebra_identity(
        runtime=runtime,
        identity=identity,
        config=config,
        locked=locked,
    )


def test_receipt_contains_runtime_identity_and_detects_environment_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])
    monkeypatch.setattr(
        module.metadata,
        "version",
        lambda name: locked[name.lower().replace("_", "-")]["version"],
    )
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.12.11")
    env = dict(config["determinism"])
    env["OMP_NUM_THREADS"] = "8"

    receipt = module.build_receipt(
        config,
        repo_root=ROOT,
        environ=env,
        source_sha="a" * 40,
    )

    runtime = receipt["runtime"]
    assert receipt["source_commit_sha"] == "a" * 40
    assert set(("python", "packages", "os", "libc", "blas", "lapack")) <= set(runtime)
    assert (
        runtime["packages"]["numpy"]["wheel_sha256"] == locked["numpy"]["wheel_sha256"]
    )
    assert runtime["thread_limits"]["OMP_NUM_THREADS"] == "8"
    assert runtime["timezone"] == "UTC"
    assert runtime["python_hash_seed"] == "0"
    assert receipt["contract_pass"] is False
    assert "environment_mismatch:OMP_NUM_THREADS:8" in receipt["violations"]


def test_check_mode_does_not_replace_stored_receipt(tmp_path: Path) -> None:
    stored = tmp_path / "receipt.json"
    stored.write_text(json.dumps({"stale": True}), encoding="utf-8")
    before = stored.read_bytes()

    exit_code = module.main(
        [
            "--repo-root",
            str(ROOT),
            "--source-sha",
            "b" * 40,
            "--check",
            str(stored),
        ]
    )

    assert exit_code == 1
    assert stored.read_bytes() == before


def _wheel_contract(
    *,
    source_sha: str,
    source_date_epoch: int,
    wheel: Path,
) -> dict:
    wheel_hash = "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
    cases = {
        case_id: {
            "result_hash": "sha256:" + "4" * 64,
            "engineering_result_hash": "sha256:" + "5" * 64,
            "checkpoint_sha256": "sha256:" + "6" * 64,
        }
        for case_id in ("member_feature", "prescribed_settlement")
    }
    replay = {
        "schema_version": "bounded-planar-wheel-smoke.v2",
        "contract_pass": True,
        "wheel_origin": "prebuilt_exact_artifact",
        "wheel_filename": wheel.name,
        "wheel_sha256": wheel_hash,
        "installed_module": (
            "lib/python3.12/site-packages/structural_analysis/__init__.py"
        ),
        "installed_schema": (
            "lib/python3.12/site-packages/structural_analysis/"
            "schemas/model_ir_v2.schema.json"
        ),
        "installed_source_commit_sha": source_sha,
        "installed_source_date_epoch": source_date_epoch,
        "execution_count": 2,
        "exact_repeat_match": True,
        "cases": cases,
        "repeat_cases": json.loads(json.dumps(cases)),
        "claim_boundary": "test replay boundary",
    }
    first_projection_sha256 = module._canonical_hash(
        module._installed_replay_projection(replay)
    )
    repeat_projection_sha256 = module._canonical_hash(
        module._installed_replay_projection(replay, cases_key="repeat_cases")
    )
    replay["first_projection_sha256"] = first_projection_sha256
    replay["repeat_projection_sha256"] = repeat_projection_sha256
    return {
        "schema_version": "canonical-project-wheel-contract.v1",
        "source_commit_sha": source_sha,
        "source_date_epoch": source_date_epoch,
        "build": {
            "pep517_isolation": True,
            "dependency_index_access": False,
            "pip_cache": False,
            "source_export": "git-archive-exact-commit",
            "submodules_allowed": False,
            "lfs_pointer_package_inputs_allowed": False,
            "repeated_build_count": 2,
            "reproducible_wheel_bytes": True,
        },
        "dependency_wheelhouse": {
            "lock_path": "canonical/requirements.lock",
            "package_count": 4,
            "manifest_sha256": "sha256:" + "1" * 64,
            "all_locked_hashes_verified": True,
        },
        "wheel": {
            "filename": wheel.name,
            "sha256": wheel_hash,
            "repeat_sha256": wheel_hash,
            "byte_length": wheel.stat().st_size,
            "record": {
                "path": "structural_analysis-0.3.0.dist-info/RECORD",
                "sha256": "sha256:" + "2" * 64,
                "entry_count": 3,
                "all_payload_entries_sha256_verified": True,
                "source_identity_member": (
                    "structural_analysis/_canonical_build_identity.py"
                ),
            },
        },
        "installed_replay": replay,
        "contract_pass": True,
        "violations": [],
        "claim_boundary": "test wheel boundary",
    }


def _record_hash(payload: bytes) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
    )


def _write_valid_wheel(
    path: Path,
    *,
    source_sha: str,
    source_date_epoch: int,
) -> None:
    identity_name = "structural_analysis/_canonical_build_identity.py"
    identity = (
        "# Generated only inside the exact canonical wheel build.\n"
        f'SOURCE_COMMIT_SHA = "{source_sha}"\n'
        f"SOURCE_DATE_EPOCH = {source_date_epoch}\n"
    ).encode()
    payloads = (
        ("structural_analysis/__init__.py", b"__version__ = 'test'\n"),
        (identity_name, identity),
    )
    record_name = "structural_analysis-0.3.0.dist-info/RECORD"
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for name, payload in payloads:
        writer.writerow([name, f"sha256={_record_hash(payload)}", len(payload)])
    writer.writerow([record_name, "", ""])
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in payloads:
            archive.writestr(name, payload)
        archive.writestr(record_name, buffer.getvalue())


def test_persisted_bundle_validator_rechecks_raw_wheel_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sha = "a" * 40
    source_date_epoch = 123
    for relative in (
        "canonical/verification-environment.v1.json",
        "canonical/requirements-cp312-manylinux2014-x86_64.lock",
        "canonical/canonical-project-wheel-contract.v1.schema.json",
        "canonical/canonical-verification-receipt.v1.schema.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    config = module.load_config(
        tmp_path / "canonical/verification-environment.v1.json",
        repo_root=tmp_path,
    )
    locked = module.load_lock(
        tmp_path / "canonical/requirements-cp312-manylinux2014-x86_64.lock"
    )
    wheel = tmp_path / ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    _write_valid_wheel(
        wheel,
        source_sha=source_sha,
        source_date_epoch=source_date_epoch,
    )
    contract = _wheel_contract(
        source_sha=source_sha,
        source_date_epoch=source_date_epoch,
        wheel=wheel,
    )
    from scripts.build_canonical_project_wheel import validate_wheel_record

    contract["wheel"]["record"] = validate_wheel_record(
        wheel,
        source_sha=source_sha,
        source_date_epoch=source_date_epoch,
    )
    contract["dependency_wheelhouse"]["lock_path"] = config["dependency_lock"]["path"]
    linear_algebra_runtime = _linear_algebra_runtime(locked)
    receipt = {
        "schema_version": "canonical-verification-receipt.v1",
        "contract_profile": module.INSTALLED_WHEEL_PROFILE,
        "source_commit_sha": source_sha,
        "source_checkout_head_sha": source_sha,
        "source_date_epoch": source_date_epoch,
        "container": config["container"],
        "project_wheel": contract,
        "runtime": {
            "python": {**config["python"], "executable": "/usr/local/bin/python"},
            "packages": {
                name: {
                    "version": row["version"],
                    "expected_version": row["version"],
                    "wheel_sha256": row["wheel_sha256"],
                }
                for name, row in locked.items()
            },
            "os": {},
            "libc": {},
            **linear_algebra_runtime,
            "thread_limits": {
                key: config["determinism"][key]
                for key in (
                    "OPENBLAS_NUM_THREADS",
                    "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS",
                )
            },
            "locale": {
                "LANG": config["determinism"]["LANG"],
                "LC_ALL": config["determinism"]["LC_ALL"],
                "active": "C.UTF-8",
            },
            "timezone": config["determinism"]["TZ"],
            "python_hash_seed": config["determinism"]["PYTHONHASHSEED"],
            "numpy_runtime_version": locked["numpy"]["version"],
            "scipy_runtime_version": locked["scipy"]["version"],
        },
        "contract_pass": True,
        "violations": [],
    }
    contract_path = tmp_path / ".ci/canonical-project-wheel-contract.json"
    receipt_path = (
        tmp_path
        / "artifacts/manifests/canonical_verification_environment.current.v1.json"
    )
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert (
        module.validate_persisted_canonical_bundle(
            repo_root=tmp_path,
            receipt_path=receipt_path,
            project_wheel_contract_path=contract_path,
            project_wheel_path=wheel,
            source_sha=source_sha,
            source_date_epoch=source_date_epoch,
        )
        == []
    )

    tampered = json.loads(json.dumps(receipt))
    tampered["runtime"]["linear_algebra_shared_libraries"][0]["sha256"] = "3" * 64
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert "canonical_receipt_linear_algebra_runtime_binding_mismatch" in (
        module.validate_persisted_canonical_bundle(
            repo_root=tmp_path,
            receipt_path=receipt_path,
            project_wheel_contract_path=contract_path,
            project_wheel_path=wheel,
            source_sha=source_sha,
            source_date_epoch=source_date_epoch,
        )
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    dag_path = tmp_path / "canonical/generated-artifact-dag.v1.json"
    dag_path.write_bytes(
        (ROOT / "canonical/generated-artifact-dag.v1.json").read_bytes()
    )
    nodes = dag_module.load_dag(dag_path)
    for node in nodes:
        for relative in [*node["inputs"], *node["outputs"]]:
            path = tmp_path / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative, encoding="utf-8")
    monkeypatch.setattr(module, "_git_source_sha", lambda repo_root: source_sha)
    monkeypatch.setattr(
        module,
        "_source_commit_timestamp",
        lambda repo_root, value: source_date_epoch,
    )
    monkeypatch.setattr(
        dag_module,
        "_validate_capability_registry_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        dag_module,
        "_validate_capability_surfaces_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        dag_module,
        "_validate_release_artifact_bindings",
        lambda repo_root: [],
    )
    fresh_snapshot = dag_module.build_snapshot(
        nodes,
        repo_root=tmp_path,
        candidate=True,
    )
    fresh_bindings = dag_module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    fresh_report = dag_module.evaluate_snapshot(
        fresh_snapshot,
        fresh_snapshot,
        current_bindings=fresh_bindings,
    )
    assert fresh_report["scope_pass"] is True

    receipt["source_checkout_head_sha"] = "b" * 40
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    stale_receipt_snapshot = dag_module.build_snapshot(
        nodes,
        repo_root=tmp_path,
        candidate=True,
    )
    stale_receipt_bindings = dag_module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    stale_receipt_report = dag_module.evaluate_snapshot(
        stale_receipt_snapshot,
        stale_receipt_snapshot,
        current_bindings=stale_receipt_bindings,
    )
    assert (
        "current_binding:canonical_receipt_source_checkout_head_sha_mismatch"
        in (stale_receipt_report["nodes"]["verification-receipts"]["reasons"])
    )
    assert stale_receipt_report["scope_pass"] is False
    receipt["source_checkout_head_sha"] = source_sha
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    wheel.write_bytes(wheel.read_bytes() + b"tampered")
    violations = module.validate_persisted_canonical_bundle(
        repo_root=tmp_path,
        receipt_path=receipt_path,
        project_wheel_contract_path=contract_path,
        project_wheel_path=wheel,
        source_sha=source_sha,
        source_date_epoch=source_date_epoch,
    )
    assert "project_wheel_artifact_sha256_mismatch" in violations
    stale_snapshot = dag_module.build_snapshot(
        nodes,
        repo_root=tmp_path,
        candidate=True,
    )
    stale_bindings = dag_module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    stale_report = dag_module.evaluate_snapshot(
        stale_snapshot,
        stale_snapshot,
        current_bindings=stale_bindings,
    )
    assert stale_report["nodes"]["verification-receipts"]["status"] == "stale"
    assert (
        "current_binding:project_wheel_artifact_sha256_mismatch"
        in (stale_report["nodes"]["verification-receipts"]["reasons"])
    )
    assert stale_report["scope_pass"] is False


def test_project_wheel_contract_is_bound_to_raw_artifact_and_source(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    contract = _wheel_contract(
        source_sha="a" * 40,
        source_date_epoch=123,
        wheel=wheel,
    )

    assert (
        module.validate_project_wheel_contract(
            contract,
            wheel_path=wheel,
            source_sha="a" * 40,
            source_date_epoch=123,
        )
        == []
    )

    wheel.write_bytes(b"tampered-wheel")
    violations = module.validate_project_wheel_contract(
        contract,
        wheel_path=wheel,
        source_sha="b" * 40,
        source_date_epoch=123,
    )
    assert "project_wheel_source_sha_mismatch" in violations
    assert "project_wheel_artifact_sha256_mismatch" in violations

    schema_invalid = _wheel_contract(
        source_sha="a" * 40,
        source_date_epoch=123,
        wheel=wheel,
    )
    schema_invalid.pop("claim_boundary")
    violations = module.validate_project_wheel_contract(
        schema_invalid,
        wheel_path=wheel,
        source_sha="a" * 40,
        source_date_epoch=123,
    )
    assert "project_wheel_schema_invalid" in violations


def test_project_wheel_contract_recomputes_repeat_replay_evidence(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    contract = _wheel_contract(
        source_sha="a" * 40,
        source_date_epoch=123,
        wheel=wheel,
    )

    replay = contract["installed_replay"]
    replay["repeat_cases"]["member_feature"]["checkpoint_sha256"] = "sha256:" + "9" * 64
    violations = module.validate_project_wheel_contract(
        contract,
        wheel_path=wheel,
        source_sha="a" * 40,
        source_date_epoch=123,
    )
    assert "installed_wheel_replay_projection_hash_invalid" in violations
    assert "installed_wheel_replay_repeat_evidence_mismatch" in violations

    replay["repeat_projection_sha256"] = module._canonical_hash(
        module._installed_replay_projection(replay, cases_key="repeat_cases")
    )
    violations = module.validate_project_wheel_contract(
        contract,
        wheel_path=wheel,
        source_sha="a" * 40,
        source_date_epoch=123,
    )
    assert "installed_wheel_replay_projection_hash_invalid" not in violations
    assert "installed_wheel_replay_repeat_evidence_mismatch" in violations


def test_project_wheel_schema_requires_two_exact_replay_case_sets(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    contract = _wheel_contract(
        source_sha="a" * 40,
        source_date_epoch=123,
        wheel=wheel,
    )
    schema = json.loads(
        (ROOT / "canonical/canonical-project-wheel-contract.v1.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(contract)) == []

    missing_repeat = json.loads(json.dumps(contract))
    missing_repeat["installed_replay"].pop("repeat_cases")
    assert list(validator.iter_errors(missing_repeat))

    extra_case = json.loads(json.dumps(contract))
    extra_case["installed_replay"]["repeat_cases"]["unsupported"] = {
        "result_hash": "sha256:" + "1" * 64,
        "engineering_result_hash": "sha256:" + "2" * 64,
        "checkpoint_sha256": "sha256:" + "3" * 64,
    }
    assert list(validator.iter_errors(extra_case))

    extra_hash_claim = json.loads(json.dumps(contract))
    extra_hash_claim["installed_replay"]["cases"]["member_feature"][
        "unverified_hash"
    ] = "sha256:" + "7" * 64
    assert list(validator.iter_errors(extra_hash_claim))


def _write_linear_algebra_wheel(
    path: Path,
    *,
    member: str,
    payload: bytes,
) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_linear_algebra_identity_binds_loaded_bytes_to_exact_locked_wheels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    numpy_payload = b"exact numpy openblas shared library"
    scipy_payload = b"exact scipy openblas shared library"
    numpy_name = "libopenblas-numpy.so"
    scipy_name = "libopenblas-scipy.so"
    numpy_hash = _write_linear_algebra_wheel(
        wheelhouse / "numpy-1-cp312-cp312-manylinux2014_x86_64.whl",
        member=f"numpy.libs/{numpy_name}",
        payload=numpy_payload,
    )
    scipy_hash = _write_linear_algebra_wheel(
        wheelhouse / "scipy-1-cp312-cp312-manylinux2014_x86_64.whl",
        member=f"scipy.libs/{scipy_name}",
        payload=scipy_payload,
    )
    locked = {
        "numpy": {"version": "1", "wheel_sha256": numpy_hash},
        "scipy": {"version": "1", "wheel_sha256": scipy_hash},
    }
    config = {
        "linear_algebra": {
            "provider_family": "openblas",
            "wheel_bound_distributions": ["numpy", "scipy"],
        },
        "determinism": {"OPENBLAS_CORETYPE": "Haswell"},
    }
    monkeypatch.setattr(module, "_exercise_linear_algebra", lambda: None)
    monkeypatch.setattr(
        module,
        "_numpy_build_dependency",
        lambda role: {
            "name": "scipy-openblas",
            "version": "0.3.test",
            "found": True,
            "detection method": "pkgconfig",
            "openblas configuration": f"OpenBLAS test {role}",
        },
    )
    monkeypatch.setattr(
        module,
        "_linear_algebra_libraries",
        lambda: [
            {
                "path": f"/site-packages/numpy.libs/{numpy_name}",
                "sha256": hashlib.sha256(numpy_payload).hexdigest(),
            },
            {
                "path": f"/site-packages/scipy.libs/{scipy_name}",
                "sha256": hashlib.sha256(scipy_payload).hexdigest(),
            },
        ],
    )

    identity, violations = module.build_linear_algebra_identity(
        config,
        locked=locked,
        wheelhouse=wheelhouse,
        openblas_coretype="Haswell",
    )

    assert violations == []
    assert identity["wheel_membership_verified"] is True
    assert identity["openblas_coretype"] == "Haswell"
    assert identity["fingerprint_sha256"].startswith("sha256:")
    assert {row["distribution"] for row in identity["loaded_libraries"]} == {
        "numpy",
        "scipy",
    }
    runtime = {
        "blas": module._numpy_build_dependency("blas"),
        "lapack": module._numpy_build_dependency("lapack"),
        "linear_algebra_shared_libraries": module._linear_algebra_libraries(),
    }
    assert (
        module._validate_persisted_linear_algebra_identity(
            runtime=runtime,
            identity=identity,
            config=config,
            locked=locked,
        )
        == []
    )

    monkeypatch.setattr(
        module,
        "_numpy_build_dependency",
        lambda role: {
            "name": "generic-blas",
            "version": "1",
            "found": True,
            "detection method": "internal",
            "openblas configuration": "unknown",
        },
    )
    identity, violations = module.build_linear_algebra_identity(
        config,
        locked=locked,
        wheelhouse=wheelhouse,
        openblas_coretype="Haswell",
    )
    assert any("linear_algebra_provider_mismatch" in row for row in violations)
    assert identity["wheel_membership_verified"] is False

    monkeypatch.setattr(
        module,
        "_linear_algebra_libraries",
        lambda: [{"path": f"/tmp/{numpy_name}", "sha256": "0" * 64}],
    )
    identity, violations = module.build_linear_algebra_identity(
        config,
        locked=locked,
        wheelhouse=wheelhouse,
        openblas_coretype="Haswell",
    )
    assert identity["wheel_membership_verified"] is False
    assert any("library_not_wheel_bound" in violation for violation in violations)


def test_installed_wheel_profile_rejects_claimed_sha_not_checkout_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])
    monkeypatch.setattr(
        module.metadata,
        "version",
        lambda name: locked[name.lower().replace("_", "-")]["version"],
    )
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.12.11")
    monkeypatch.setattr(module, "_git_source_sha", lambda repo_root: "b" * 40)
    monkeypatch.setattr(module, "_source_commit_timestamp", lambda *args: 123)
    monkeypatch.setattr(
        module,
        "build_linear_algebra_identity",
        lambda *args, **kwargs: (
            {"wheel_membership_verified": True},
            [],
        ),
    )
    env = {**config["determinism"], "SOURCE_DATE_EPOCH": "123"}

    receipt = module.build_receipt(
        config,
        repo_root=ROOT,
        environ=env,
        source_sha="a" * 40,
    )

    assert receipt["source_commit_sha"] == "a" * 40
    assert receipt["source_checkout_head_sha"] == "b" * 40
    assert any(
        violation.startswith("source_checkout_head_mismatch:")
        for violation in receipt["violations"]
    )
    assert receipt["contract_pass"] is False
