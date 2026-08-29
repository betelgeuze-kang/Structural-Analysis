from __future__ import annotations

from configparser import ConfigParser
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_developer_preview_readiness import build_dataset_license_manifest  # noqa: E402
from structural_analysis.benchmark.factory import (  # noqa: E402
    build_manifest,
    generated_benchmark_factory_cases,
)


LICENSE_REF = "LicenseRef-Repository-Default-No-License"
NPM_LICENSE_REF = "SEE LICENSE IN LICENSE"
NO_GRANT_FRAGMENTS = (
    "All rights reserved.",
    "No permission is granted",
    "except under a separate written agreement",
    "It is not evidence of product-license approval",
)


def _toml(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def test_repository_license_remains_the_no_grant_authority() -> None:
    license_path = ROOT / "LICENSE"
    assert license_path.is_file()
    assert not license_path.is_symlink()
    notice = " ".join(license_path.read_text(encoding="utf-8").split())
    assert all(fragment in notice for fragment in NO_GRANT_FRAGMENTS)


def test_rights_holder_trust_root_is_checked_in_but_grants_no_authority() -> None:
    trust_root = json.loads(
        (
            ROOT / "canonical/rights-holder-license-trust-root.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert trust_root["repository_id"] == (
        "betelgeuze-kang/structural-analysis"
    )
    assert trust_root["approved_signers"] == []
    assert trust_root["revoked_signer_ids"] == []
    assert trust_root["revoked_decision_ids"] == []
    assert "grants no" in trust_root["claim_boundary"].lower()
    decision_schema = json.loads(
        (
            ROOT / "canonical/rights-holder-license-decision.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    trust_schema = json.loads(
        (
            ROOT / "canonical/rights-holder-license-trust-root.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(decision_schema)
    Draft202012Validator.check_schema(trust_schema)
    Draft202012Validator(trust_schema).validate(trust_root)


def test_python_package_metadata_references_the_repository_license() -> None:
    project = _toml(ROOT / "pyproject.toml")["project"]
    assert isinstance(project, dict)
    assert project["license"] == LICENSE_REF
    assert project["license-files"] == ["LICENSE"]

    legacy = ConfigParser()
    legacy.read(ROOT / "setup.cfg", encoding="utf-8")
    assert legacy.get("metadata", "license") == LICENSE_REF
    assert legacy.get("metadata", "license_files") == "LICENSE"


def test_private_node_package_and_lock_reference_the_repository_license() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["license"] == NPM_LICENSE_REF
    assert lock["license"] == NPM_LICENSE_REF
    assert lock["packages"][""]["license"] == NPM_LICENSE_REF

    dependency_rows = {
        path: row
        for path, row in lock["packages"].items()
        if path and isinstance(row, dict)
    }
    assert dependency_rows
    assert all(
        isinstance(row.get("license"), str) and row["license"].strip()
        for row in dependency_rows.values()
    )
    assert all(
        isinstance(row.get("integrity"), str)
        and row["integrity"].startswith("sha512-")
        for row in dependency_rows.values()
    )


def test_runtime_sbom_does_not_promote_third_party_or_release_authority() -> None:
    sbom = json.loads(
        (ROOT / "implementation/phase1/runtime_sbom.json").read_text(
            encoding="utf-8"
        )
    )
    assert sbom["claim_boundary"]["not_granted"] == [
        "license or redistribution clearance",
        "product signing authority",
        "release authority",
    ]
    assert sbom["authority"] == {
        "product_license_approval": False,
        "commercial_use_authority": False,
        "redistribution_authority": False,
        "third_party_redistribution_clearance": "not_established",
        "release_authority": False,
    }


def test_every_first_party_rust_package_references_the_repository_license() -> None:
    workspace = _toml(ROOT / "native/Cargo.toml")
    workspace_package = workspace["workspace"]["package"]
    assert workspace_package["license-file"] == "../LICENSE"
    assert workspace_package["publish"] is False
    assert "license" not in workspace_package

    for relative in workspace["workspace"]["members"]:
        package = _toml(ROOT / "native" / relative / "Cargo.toml")["package"]
        assert package["license-file"] == {"workspace": True}
        assert package["publish"] == {"workspace": True}
        assert "license" not in package

    standalone = (
        ROOT / "implementation/phase1/mgt_hip_full_residual_ffi/Cargo.toml",
        ROOT / "implementation/phase1/structural_runtime_ffi/Cargo.toml",
    )
    for manifest in standalone:
        package = _toml(manifest)["package"]
        assert package["license-file"] == "../../../LICENSE"
        assert package["publish"] is False
        assert "license" not in package
        assert (manifest.parent / package["license-file"]).resolve() == (
            ROOT / "LICENSE"
        ).resolve()


def test_repo_generated_benchmarks_are_technical_provenance_only() -> None:
    cases = generated_benchmark_factory_cases()
    manifest = build_manifest(cases)

    assert manifest["technical_provenance_only"] is True
    assert manifest["repo_generated_bundle_eligible"] is False
    assert manifest["redistribution_authority"] is False
    assert manifest["commercial_use_authority"] is False
    assert manifest["release_authority"] is False
    for row in manifest["rows"]:
        assert row["license"] == {
            "id": LICENSE_REF,
            "spdx": LICENSE_REF,
            "local_execution_allowed": False,
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "approval_status": "signed_rights_holder_decision_required",
        }
    for case in cases:
        metadata = case.payload["metadata"]
        assert metadata["license_id"] == LICENSE_REF
        assert metadata["local_execution_allowed"] is False
        assert metadata["redistribution_allowed"] is False
        assert metadata["commercial_use_allowed"] is False
        assert metadata["rights_holder_approval_status"] == (
            "signed_rights_holder_decision_required"
        )


def test_dataset_manifest_never_self_approves_repo_generated_bundling() -> None:
    payload = build_dataset_license_manifest(repo_root=ROOT)
    analytic = next(
        row for row in payload["sources"] if row["source_id"] == "analytic-small"
    )

    assert analytic["license"] == LICENSE_REF
    assert analytic["local_execution_allowed"] is False
    assert analytic["redistribution_allowed"] is False
    assert analytic["commercial_use_allowed"] is False
    assert analytic["rights_holder_approval_status"] == (
        "signed_rights_holder_decision_required"
    )
    seed_contract = payload["manifest_policy_contract"][
        "developer_preview_seed_contract"
    ]
    assert seed_contract["technical_provenance_source_ids"] == ["analytic-small"]
    assert seed_contract["bundle_eligible_source_ids"] == []
    assert seed_contract["redistribution_authority"] is False
    assert seed_contract["commercial_use_authority"] is False
    assert seed_contract["release_authority"] is False
