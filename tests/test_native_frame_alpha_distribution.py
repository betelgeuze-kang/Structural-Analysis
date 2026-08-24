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
    assert first["authority"] == distribution.SMOKE_AUTHORITY

    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(set(names)) == 10
        assert names[-1].endswith("/manifest.json")
        assert all(".." not in Path(name).parts for name in names)
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

    receipt = distribution.verify_workstation_distribution(archive_path=archive)
    _validator("frame_alpha_workstation_distribution_smoke_v2.schema.json").validate(
        receipt
    )
    assert receipt["checks"]["static_index"] == "passed"
    assert receipt["checks"]["static_asset"] == "passed"
    assert receipt["checks"]["capabilities"] == "passed"
    assert receipt["authority"] == distribution.WORKSTATION_SMOKE_AUTHORITY

    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(set(names)) == 15
        assert names[-1].endswith("/manifest.json")
        assert any(name.endswith("/workbench/index.html") for name in names)
        assert any(name.endswith("/workbench/assets/app.js") for name in names)
        assert any(
            name.endswith("/schemas/native_linear_frame3d_job_view_v2.schema.json")
            for name in names
        )


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
