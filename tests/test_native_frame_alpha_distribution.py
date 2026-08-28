from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import warnings
import zipfile

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_native_frame_alpha_distribution.py"
SPEC = importlib.util.spec_from_file_location(
    "build_native_frame_alpha_distribution", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
distribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = distribution
SPEC.loader.exec_module(distribution)
TRANSITION_SCRIPT = (
    ROOT / "scripts/build_native_frame_alpha_portable_transition_evidence.py"
)
TRANSITION_SPEC = importlib.util.spec_from_file_location(
    "build_native_frame_alpha_portable_transition_evidence_distribution_test",
    TRANSITION_SCRIPT,
)
assert TRANSITION_SPEC is not None and TRANSITION_SPEC.loader is not None
transition = importlib.util.module_from_spec(TRANSITION_SPEC)
sys.modules[TRANSITION_SPEC.name] = transition
TRANSITION_SPEC.loader.exec_module(transition)


@pytest.fixture(scope="module")
def release_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("frame-alpha-release-target")
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(ROOT / "native/Cargo.toml"),
            "--package",
            "structural-cli",
            "--release",
            "--locked",
            "--target-dir",
            str(target),
        ],
        cwd=ROOT,
        check=True,
        timeout=600,
    )
    executable = target / "release/structural-cli"
    assert executable.is_file()
    return executable


@pytest.fixture()
def built_archives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    release_cli: Path,
) -> tuple[Path, Path, dict[str, object]]:
    monkeypatch.setattr(distribution, "_verify_source_checkout", lambda *_args: None)
    commit = "1" * 40
    tree = "2" * 40
    outputs = (tmp_path / "first.zip", tmp_path / "second.zip")
    manifests = [
        distribution.build_distribution(
            structural_cli=release_cli,
            platform_tag="linux-x86_64-gnu",
            source_commit=commit,
            source_tree=tree,
            output=output,
        )
        for output in outputs
    ]
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert manifests[0] == manifests[1]
    return outputs[0], outputs[1], manifests[0]


@pytest.fixture()
def synthetic_workbench(tmp_path: Path) -> Path:
    workbench = tmp_path / "workbench"
    assets = workbench / "assets"
    assets.mkdir(parents=True)
    (workbench / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/app.js"></script>\n',
        encoding="utf-8",
    )
    (assets / "app.js").write_text(
        'const submissionUrl = "/api/v1/frame3d/jobs";\n', encoding="utf-8"
    )
    (assets / "app.css").write_text("body { color: #111; }\n", encoding="utf-8")
    return workbench


@pytest.fixture()
def built_workstation_archives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    release_cli: Path,
    synthetic_workbench: Path,
) -> tuple[Path, Path, dict[str, object]]:
    monkeypatch.setattr(distribution, "_verify_source_checkout", lambda *_args: None)

    def smoke(*, binary: Path, workbench: Path, directory: Path) -> dict[str, object]:
        del binary, directory
        index = (workbench / "index.html").read_bytes()
        asset = (workbench / "assets/app.js").read_bytes()
        return {
            "startup_schema": "structural-native-frame-alpha-workstation-host.v2",
            "service_profile": "loopback_worker_process_cancellation.v2",
            "static_index": "passed",
            "static_asset": "passed",
            "capabilities": "passed",
            "index_sha256": distribution._sha256_bytes(index),
            "asset_path": "/assets/app.js",
            "asset_sha256": distribution._sha256_bytes(asset),
        }

    monkeypatch.setattr(distribution, "_smoke_extracted_workstation", smoke)
    commit = "3" * 40
    tree = "4" * 40
    outputs = (tmp_path / "workstation-first.zip", tmp_path / "workstation-second.zip")
    manifests = [
        distribution.build_workstation_distribution(
            structural_cli=release_cli,
            workbench=synthetic_workbench,
            platform_tag="linux-x86_64-gnu",
            source_commit=commit,
            source_tree=tree,
            output=output,
        )
        for output in outputs
    ]
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert manifests[0] == manifests[1]
    return outputs[0], outputs[1], manifests[0]


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "native/distribution" / name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_distribution_is_deterministic_strict_and_runs_extracted_workflow(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, manifest = built_archives
    _validator("frame_alpha_distribution_manifest_v1.schema.json").validate(manifest)

    first = distribution.verify_distribution(archive_path=archive)
    second = distribution.verify_distribution(archive_path=archive)
    assert first == second
    _validator("frame_alpha_distribution_smoke_v1.schema.json").validate(first)
    assert first["checks"]["model_validation"] == "analysis_ready"
    assert first["checks"]["analysis_to_workbench_bundle"] == "passed"
    assert first["checks"]["license_no_grant_policy"] == "passed"
    assert first["checks"]["license_sbom"] == "passed"
    assert first["checks"]["release_clearance"] == "blocked"
    assert first["authority"] == distribution.SMOKE_AUTHORITY
    assert manifest["license"]["repository_posture"] == (
        "all_rights_reserved_no_license_granted"
    )
    assert manifest["license"]["release_clearance"] == "blocked"
    assert manifest["license"]["product_license_approval"] is False

    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(set(names)) == 13
        assert names[-1].endswith("/manifest.json")
        assert all(".." not in Path(name).parts for name in names)
        sbom_name = next(
            name for name in names if name.endswith("/SBOM.native-license.json")
        )
        sbom = json.loads(package.read(sbom_name))
        assert sbom["contract_pass"] is True
        assert sbom["package_count"] == len(sbom["packages"]) == 115
        assert sbom["external_dependency_count"] == 109
        assert sbom["first_party_license"]["workspace_package_count"] == 6
        assert sbom["release_clearance"]["status"] == "blocked"
        assert any(name.endswith("/schemas/external_linear_frame3d_reference_v1.schema.json") for name in names)
        assert any(name.endswith("/schemas/linear_frame3d_comparison_ir_v1.schema.json") for name in names)
        assert any(name.endswith("/schemas/native_linear_frame3d_job_submission_v1.schema.json") for name in names)


def test_distribution_rejects_archive_content_tampering(
    tmp_path: Path,
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    source, _duplicate, _manifest = built_archives
    tampered = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(tampered, "x", compression=zipfile.ZIP_DEFLATED) as changed,
    ):
        for info in original.infolist():
            payload = original.read(info)
            if info.filename.endswith("frame-alpha-cantilever.model-ir.json"):
                payload += b"\n"
            changed.writestr(info, payload)

    with pytest.raises(
        distribution.DistributionError, match="archive_file_binding_invalid"
    ):
        distribution.verify_distribution(archive_path=tampered)


def test_distribution_rejects_duplicate_archive_paths(
    tmp_path: Path,
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    source, _duplicate, _manifest = built_archives
    duplicated = tmp_path / "duplicated.zip"
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(duplicated, "x", compression=zipfile.ZIP_DEFLATED) as changed,
    ):
        infos = original.infolist()
        for info in infos:
            changed.writestr(info, original.read(info))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            changed.writestr(infos[0], original.read(infos[0]))

    with pytest.raises(distribution.DistributionError, match="archive_shape_invalid"):
        distribution.verify_distribution(archive_path=duplicated)


def test_distribution_schema_rejects_authority_promotion(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    _archive, _duplicate, manifest = built_archives
    promoted = deepcopy(manifest)
    promoted["authority"]["release_readiness"] = "authoritative"

    with pytest.raises(ValidationError):
        _validator("frame_alpha_distribution_manifest_v1.schema.json").validate(
            promoted
        )


def test_distribution_schema_rejects_license_approval_promotion(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    _archive, _duplicate, manifest = built_archives
    promoted = deepcopy(manifest)
    promoted["license"]["commercial_redistribution_approved"] = True
    promoted["license"]["release_clearance"] = "passed"

    with pytest.raises(ValidationError):
        _validator("frame_alpha_distribution_manifest_v1.schema.json").validate(
            promoted
        )


def test_distribution_rejects_self_consistent_license_semantic_promotion(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, manifest = built_archives
    with zipfile.ZipFile(archive) as package:
        root = manifest["package_id"]
        payloads = {
            path: package.read(f"{root}/{path}")
            for path in (
                "LICENSE",
                distribution.LICENSE_SBOM_PATH,
                distribution.PACKAGED_CARGO_LOCK_PATH,
                distribution.PACKAGED_POLICY_PATH,
            )
        }
    promoted = json.loads(payloads[distribution.LICENSE_SBOM_PATH])
    promoted["release_clearance"]["status"] = "passed"
    promoted["release_clearance"]["commercial_redistribution_approved"] = True
    payloads[distribution.LICENSE_SBOM_PATH] = (
        distribution._canonical_bytes(promoted) + b"\n"
    )

    with pytest.raises(
        distribution.DistributionError,
        match="distribution_license_sbom_contract_invalid",
    ):
        distribution._validate_packaged_license(
            manifest,
            payloads,
            label="distribution",
        )


def test_distribution_rejects_coherently_rehashed_appended_license_grant(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, original_manifest = built_archives
    with zipfile.ZipFile(archive) as package:
        root = original_manifest["package_id"]
        payloads = {
            path: package.read(f"{root}/{path}")
            for path in (
                "LICENSE",
                distribution.LICENSE_SBOM_PATH,
                distribution.PACKAGED_CARGO_LOCK_PATH,
                distribution.PACKAGED_POLICY_PATH,
            )
        }

    forged_manifest = deepcopy(original_manifest)
    license_bytes = (
        payloads["LICENSE"]
        + b"\nPermission is hereby granted to use this software.\n"
    )
    payloads["LICENSE"] = license_bytes
    sbom = json.loads(payloads[distribution.LICENSE_SBOM_PATH])
    sbom["first_party_license"]["repository_license"]["sha256"] = (
        distribution._sha256_bytes(license_bytes)
    )
    sbom_bytes = distribution._canonical_bytes(sbom) + b"\n"
    payloads[distribution.LICENSE_SBOM_PATH] = sbom_bytes
    forged_manifest["license"]["license_sha256"] = distribution._sha256_bytes(
        license_bytes
    )
    forged_manifest["license"]["sbom_sha256"] = distribution._sha256_bytes(
        sbom_bytes
    )

    with pytest.raises(
        distribution.DistributionError,
        match="packaged_repository_license_not_pinned_trusted_baseline",
    ):
        distribution._validate_packaged_license(
            forged_manifest,
            payloads,
            label="distribution",
        )


def test_distribution_rejects_forged_or_incomplete_locked_sbom(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, original_manifest = built_archives
    with zipfile.ZipFile(archive) as package:
        root = original_manifest["package_id"]
        original_payloads = {
            path: package.read(f"{root}/{path}")
            for path in (
                "LICENSE",
                distribution.LICENSE_SBOM_PATH,
                distribution.PACKAGED_CARGO_LOCK_PATH,
                distribution.PACKAGED_POLICY_PATH,
            )
        }

    def rejected(
        *,
        mutate_sbom: object | None = None,
        mutate_lock: bytes | None = None,
        mutate_policy: bytes | None = None,
    ) -> None:
        manifest = deepcopy(original_manifest)
        payloads = dict(original_payloads)
        if callable(mutate_sbom):
            sbom = json.loads(payloads[distribution.LICENSE_SBOM_PATH])
            mutate_sbom(sbom)
            payloads[distribution.LICENSE_SBOM_PATH] = (
                distribution._canonical_bytes(sbom) + b"\n"
            )
            manifest["license"]["sbom_sha256"] = distribution._sha256_bytes(
                payloads[distribution.LICENSE_SBOM_PATH]
            )
        if mutate_lock is not None:
            payloads[distribution.PACKAGED_CARGO_LOCK_PATH] = mutate_lock
        if mutate_policy is not None:
            payloads[distribution.PACKAGED_POLICY_PATH] = mutate_policy
        with pytest.raises(
            distribution.DistributionError,
            match="distribution_license_sbom_semantic_invalid",
        ):
            distribution._validate_packaged_license(
                manifest, payloads, label="distribution"
            )

    def empty_inventory(sbom: dict[str, object]) -> None:
        sbom["packages"] = []
        sbom["package_count"] = 0
        sbom["external_dependency_count"] = 0

    rejected(mutate_sbom=empty_inventory)

    def unknown_license(sbom: dict[str, object]) -> None:
        row = next(item for item in sbom["packages"] if item["external"])
        row["license"] = "UNKNOWN"
        row["license_ids"] = ["UNKNOWN"]
        row["license_allowed"] = True

    rejected(mutate_sbom=unknown_license)

    def git_source(sbom: dict[str, object]) -> None:
        row = next(item for item in sbom["packages"] if item["external"])
        row["source"] = "git+https://example.invalid/forged"
        row["source_allowed"] = True

    rejected(mutate_sbom=git_source)

    def msrv_promotion(sbom: dict[str, object]) -> None:
        row = next(item for item in sbom["packages"] if item["external"])
        row["rust_version"] = "999.0.0"
        row["msrv_allowed"] = True

    rejected(mutate_sbom=msrv_promotion)

    rejected(
        mutate_sbom=lambda sbom: sbom.__setitem__(
            "package_count", int(sbom["package_count"]) - 1
        )
    )

    def graph_tamper(sbom: dict[str, object]) -> None:
        row = next(item for item in sbom["packages"] if item["dependencies"])
        row["dependencies"] = []

    rejected(mutate_sbom=graph_tamper)

    def input_hash_tamper(sbom: dict[str, object]) -> None:
        sbom["inputs"]["cargo_lock"]["sha256"] = "sha256:" + "0" * 64

    rejected(mutate_sbom=input_hash_tamper)
    rejected(
        mutate_lock=original_payloads[distribution.PACKAGED_CARGO_LOCK_PATH].replace(
            b"version = 3", b"version = 2", 1
        )
    )

    policy = json.loads(original_payloads[distribution.PACKAGED_POLICY_PATH])
    policy["allowed_license_ids"].append("UNKNOWN")
    rejected(mutate_policy=distribution._canonical_bytes(policy) + b"\n")


def test_distribution_rejects_coherently_replaced_lock_and_sbom(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, original_manifest = built_archives
    with zipfile.ZipFile(archive) as package:
        root = original_manifest["package_id"]
        original_payloads = {
            path: package.read(f"{root}/{path}")
            for path in (
                "LICENSE",
                distribution.LICENSE_SBOM_PATH,
                distribution.PACKAGED_CARGO_LOCK_PATH,
                distribution.PACKAGED_POLICY_PATH,
            )
        }
    original_sbom = json.loads(
        original_payloads[distribution.LICENSE_SBOM_PATH]
    )
    first_party = [
        deepcopy(row) for row in original_sbom["packages"] if not row["external"]
    ]

    def lock_bytes(extra: list[str] | None = None) -> bytes:
        parts = ["version = 3", ""]
        for row in first_party:
            name, version = row["package"].rsplit("@", 1)
            parts.extend(
                [
                    "[[package]]",
                    f"name = {json.dumps(name)}",
                    f"version = {json.dumps(version)}",
                    "",
                ]
            )
        parts.extend(extra or [])
        return ("\n".join(parts) + "\n").encode("utf-8")

    def validate_forgery(sbom: dict[str, object], forged_lock: bytes) -> str:
        sbom_bytes = distribution._canonical_bytes(sbom) + b"\n"
        payloads = dict(original_payloads)
        payloads[distribution.LICENSE_SBOM_PATH] = sbom_bytes
        payloads[distribution.PACKAGED_CARGO_LOCK_PATH] = forged_lock
        manifest = deepcopy(original_manifest)
        manifest["license"]["sbom_sha256"] = distribution._sha256_bytes(sbom_bytes)
        with pytest.raises(
            distribution.DistributionError,
            match="distribution_license_sbom_semantic_invalid",
        ) as caught:
            distribution._validate_packaged_license(
                manifest, payloads, label="distribution"
            )
        return str(caught.value)

    reduced_lock = lock_bytes()
    reduced_sbom = deepcopy(original_sbom)
    for row in first_party:
        row["dependencies"] = []
    reduced_sbom["packages"] = sorted(first_party, key=lambda row: row["package"])
    reduced_sbom["package_count"] = 6
    reduced_sbom["external_dependency_count"] = 0
    reduced_sbom["inputs"]["cargo_lock"] = {
        "path": distribution.PACKAGED_CARGO_LOCK_PATH,
        "sha256": distribution._sha256_bytes(reduced_lock),
        "format_version": 3,
        "package_count": 6,
    }
    reduced_error = validate_forgery(reduced_sbom, reduced_lock)
    assert "cargo_lock_not_pinned_trusted_baseline" in reduced_error
    assert "cargo_lock_pinned_package_count_mismatch:6!=115" in reduced_error
    assert "cargo_lock_pinned_external_count_mismatch:0!=109" in reduced_error

    invented_lock = lock_bytes(
        [
            "[[package]]",
            'name = "invented-permissive"',
            'version = "9.9.9"',
            'source = "registry+https://github.com/rust-lang/crates.io-index"',
            f'checksum = "{"1" * 64}"',
            "",
        ]
    )
    invented_sbom = deepcopy(reduced_sbom)
    invented_sbom["packages"] = sorted(
        [
            *first_party,
            {
                "package": "invented-permissive@9.9.9",
                "external": True,
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "source_allowed": True,
                "license": "MIT",
                "license_ids": ["MIT"],
                "license_allowed": True,
                "rust_version": None,
                "msrv_allowed": True,
                "exception": False,
                "checksum": "1" * 64,
                "dependencies": [],
            },
        ],
        key=lambda row: row["package"],
    )
    invented_sbom["package_count"] = 7
    invented_sbom["external_dependency_count"] = 1
    invented_sbom["inputs"]["cargo_lock"] = {
        "path": distribution.PACKAGED_CARGO_LOCK_PATH,
        "sha256": distribution._sha256_bytes(invented_lock),
        "format_version": 3,
        "package_count": 7,
    }
    invented_error = validate_forgery(invented_sbom, invented_lock)
    assert "cargo_lock_not_pinned_trusted_baseline" in invented_error


def test_distribution_rejects_coherently_replaced_dependency_policy(
    built_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, original_manifest = built_archives
    with zipfile.ZipFile(archive) as package:
        root = original_manifest["package_id"]
        payloads = {
            path: package.read(f"{root}/{path}")
            for path in (
                "LICENSE",
                distribution.LICENSE_SBOM_PATH,
                distribution.PACKAGED_CARGO_LOCK_PATH,
                distribution.PACKAGED_POLICY_PATH,
            )
        }
    policy = json.loads(payloads[distribution.PACKAGED_POLICY_PATH])
    policy["allowed_license_ids"].append("UNKNOWN")
    policy_bytes = distribution._canonical_bytes(policy) + b"\n"
    sbom = json.loads(payloads[distribution.LICENSE_SBOM_PATH])
    sbom["inputs"]["dependency_policy"]["sha256"] = (
        distribution._sha256_bytes(policy_bytes)
    )
    sbom_bytes = distribution._canonical_bytes(sbom) + b"\n"
    payloads[distribution.PACKAGED_POLICY_PATH] = policy_bytes
    payloads[distribution.LICENSE_SBOM_PATH] = sbom_bytes
    manifest = deepcopy(original_manifest)
    manifest["license"]["sbom_sha256"] = distribution._sha256_bytes(sbom_bytes)

    with pytest.raises(
        distribution.DistributionError,
        match="native_dependency_policy_not_pinned_trusted_baseline",
    ):
        distribution._validate_packaged_license(
            manifest, payloads, label="distribution"
        )


def test_distribution_source_binding_rejects_a_different_commit() -> None:
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(
        distribution.DistributionError, match="source_checkout_identity_mismatch"
    ):
        distribution._verify_source_checkout("0" * 40, tree)


def test_distribution_rejects_a_binary_for_the_wrong_platform(
    release_cli: Path,
) -> None:
    with pytest.raises(distribution.DistributionError, match="not_windows_x86_64_pe"):
        distribution._verify_binary_format(
            release_cli.read_bytes(), "windows-x86_64-msvc"
        )


def test_workstation_distribution_binds_static_build_and_extracted_host_smoke(
    built_workstation_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    archive, _duplicate, manifest = built_workstation_archives
    _validator(
        "frame_alpha_workstation_distribution_manifest_v2.schema.json"
    ).validate(manifest)
    assert manifest["workbench"]["submission_url"] == "/api/v1/frame3d/jobs"
    assert manifest["workbench"]["file_count"] == 3
    assert manifest["license"]["third_party_redistribution_clearance"] == (
        "not_established"
    )

    receipt = distribution.verify_workstation_distribution(archive_path=archive)
    _validator("frame_alpha_workstation_distribution_smoke_v2.schema.json").validate(
        receipt
    )
    assert receipt["checks"]["static_index"] == "passed"
    assert receipt["checks"]["static_asset"] == "passed"
    assert receipt["checks"]["capabilities"] == "passed"
    assert receipt["checks"]["license_no_grant_policy"] == "passed"
    assert receipt["checks"]["license_sbom"] == "passed"
    assert receipt["checks"]["release_clearance"] == "blocked"
    assert receipt["authority"] == distribution.WORKSTATION_SMOKE_AUTHORITY

    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(set(names)) == 19
        assert names[-1].endswith("/manifest.json")
        assert any(name.endswith("/LICENSE") for name in names)
        assert any(name.endswith("/SBOM.native-license.json") for name in names)
        assert any(name.endswith("/Cargo.lock") for name in names)
        assert any(name.endswith("/native/dependency-policy.json") for name in names)
        assert any(name.endswith("/workbench/index.html") for name in names)
        assert any(name.endswith("/workbench/assets/app.js") for name in names)
        assert any(
            name.endswith("/schemas/native_linear_frame3d_job_view_v2.schema.json")
            for name in names
        )
        assert any(
            name.endswith("/schemas/linear_frame3d_result_ir_v1.schema.json")
            for name in names
        )


def test_workstation_package_generation_version_is_distinct_from_cli_version(
    tmp_path: Path,
    release_cli: Path,
    synthetic_workbench: Path,
    built_workstation_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    _archive, _duplicate, baseline_manifest = built_workstation_archives
    assert isinstance(baseline_manifest["source"], dict)
    output = tmp_path / "workstation-update-generation.zip"

    manifest = distribution.build_workstation_distribution(
        structural_cli=release_cli,
        workbench=synthetic_workbench,
        platform_tag="linux-x86_64-gnu",
        source_commit="5" * 40,
        source_tree="6" * 40,
        package_version="0.1.1",
        output=output,
    )

    _validator(
        "frame_alpha_workstation_distribution_manifest_v2.schema.json"
    ).validate(manifest)
    assert manifest["package_version"] == "0.1.1"
    assert manifest["package_id"].startswith(
        "structural-frame-alpha-workstation-0.1.1-"
    )
    assert manifest["binary"]["version"] == "structural-cli 0.1.0"
    receipt = distribution.verify_workstation_distribution(archive_path=output)
    assert receipt["status"] == "pass"
    trust = transition.build_trust_input(
        baseline_archive=_archive,
        update_archive=output,
        platform_tag="linux-x86_64-gnu",
    )
    assert [row["package_version"] for row in trust["generations"]] == [
        "0.1.0",
        "0.1.1",
    ]
    assert trust["generations"][0]["source"] != trust["generations"][1]["source"]
    assert all(row["release_candidate"] is False for row in trust["generations"])


def test_workstation_distribution_rejects_static_build_without_submission_endpoint(
    tmp_path: Path,
    release_cli: Path,
    synthetic_workbench: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(distribution, "_verify_source_checkout", lambda *_args: None)
    (synthetic_workbench / "assets/app.js").write_text(
        'const submissionUrl = undefined;\n', encoding="utf-8"
    )
    with pytest.raises(
        distribution.DistributionError, match="workbench_submission_url_missing"
    ):
        distribution.build_workstation_distribution(
            structural_cli=release_cli,
            workbench=synthetic_workbench,
            platform_tag="linux-x86_64-gnu",
            source_commit="5" * 40,
            source_tree="6" * 40,
            output=tmp_path / "must-not-exist.zip",
        )


def test_workstation_distribution_rejects_packaged_asset_tampering(
    tmp_path: Path,
    built_workstation_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    source, _duplicate, _manifest = built_workstation_archives
    tampered = tmp_path / "workstation-tampered.zip"
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(tampered, "x", compression=zipfile.ZIP_DEFLATED) as changed,
    ):
        for info in original.infolist():
            payload = original.read(info)
            if info.filename.endswith("/workbench/assets/app.js"):
                payload += b"\n"
            changed.writestr(info, payload)

    with pytest.raises(
        distribution.DistributionError,
        match="workstation_archive_file_binding_invalid",
    ):
        distribution.verify_workstation_distribution(archive_path=tampered)


def test_workstation_manifest_schema_rejects_browser_authority_promotion(
    built_workstation_archives: tuple[Path, Path, dict[str, object]],
) -> None:
    _archive, _duplicate, manifest = built_workstation_archives
    promoted = deepcopy(manifest)
    promoted["authority"]["browser_execution"] = "passed"

    with pytest.raises(ValidationError):
        _validator(
            "frame_alpha_workstation_distribution_manifest_v2.schema.json"
        ).validate(promoted)
