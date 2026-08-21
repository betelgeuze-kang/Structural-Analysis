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
        assert len(names) == len(set(names)) == 9
        assert names[-1].endswith("/manifest.json")
        assert all(".." not in Path(name).parts for name in names)
        assert any(name.endswith("/schemas/external_linear_frame3d_reference_v1.schema.json") for name in names)
        assert any(name.endswith("/schemas/linear_frame3d_comparison_ir_v1.schema.json") for name in names)


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
