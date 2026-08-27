from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_current_support_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_current_support_bundle", SCRIPT)
assert SPEC is not None
current_support = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = current_support
SPEC.loader.exec_module(current_support)


def _source_identity() -> dict[str, object]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    return {"commit_sha": commit, "tree_sha": tree, "worktree_clean": True}


def _prepare_source_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    identity = _source_identity()
    fixture_file = (current_support.DEFAULT_CLIENT_FIXTURE / "model.json").as_posix()
    monkeypatch.setattr(current_support, "_git_identity", lambda: identity)
    monkeypatch.setattr(
        current_support,
        "_head_fixture_files",
        lambda _fixture: [fixture_file],
    )
    monkeypatch.chdir(ROOT)
    return identity


def test_reference_fixture_is_ready_but_never_claims_client_authenticity() -> None:
    report = current_support.validate_client_input_package(
        input_path=current_support.DEFAULT_CLIENT_FIXTURE,
        source_kind="repository_reference_fixture",
    )

    assert report["contract_pass"] is True
    assert report["status"] == "ready"
    assert report["input_binding"]["current_worktree_bound"] is True
    assert report["input_binding"]["commit_tree_bound"] is False
    assert report["claim_boundary"]["source_authority"] == (
        "repository_reference_fixture"
    )
    assert "client-source authenticity" in report["claim_boundary"]["forbidden"]


def test_current_builder_closes_53_of_53_without_promoting_child_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    output_root = tmp_path / "current-support-bundle"

    payload = current_support.build_current_support_bundle(
        output_root=output_root,
        expected_source_sha=str(identity["commit_sha"]),
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["support_bundle"]["artifact_count"] == 53
    assert payload["support_bundle"]["available_artifact_count"] == 53
    assert payload["support_bundle"]["missing_required_count"] == 0
    assert all(payload["checks"].values())
    assert set(payload["generated_inputs"]) == set(
        current_support.GENERATED_INPUT_LABELS
    )
    assert "P0 or P1 closure" in payload["claim_boundary"]["not_granted"]
    assert "human new-user observation" in payload["claim_boundary"]["not_granted"]
    assert (
        "product code signing or platform notarization"
        in payload["claim_boundary"]["not_granted"]
    )
    assert (
        "freshness or current authority of pre-existing bundled evidence"
        in payload["claim_boundary"]["not_granted"]
    )

    manifest = json.loads(
        Path(payload["support_bundle"]["manifest"]["path"]).read_text(encoding="utf-8")
    )
    generated_paths = {
        label: Path(payload["generated_inputs"][label]["path"])
        for label in current_support.GENERATED_INPUT_LABELS
    }
    assert current_support._bundle_transitive_bindings_pass(
        support_bundle=manifest,
        generated_paths=generated_paths,
    )
    manifest["artifact_rows"][0]["sha256"] = "0" * 64
    assert not current_support._bundle_transitive_bindings_pass(
        support_bundle=manifest,
        generated_paths=generated_paths,
    )

    verified = current_support.verify_current_support_bundle(
        receipt_path=output_root / current_support.RECEIPT_NAME,
        expected_source_sha=str(identity["commit_sha"]),
    )
    assert verified == payload

    tampered_receipt = json.loads(
        (output_root / current_support.RECEIPT_NAME).read_text(encoding="utf-8")
    )
    tampered_receipt["claim_boundary"]["not_granted"] = []
    tampered_receipt["artifact_hash"] = current_support._artifact_hash(tampered_receipt)
    tampered_receipt_path = output_root / "semantic-tamper-receipt.json"
    tampered_receipt_path.write_text(
        json.dumps(tampered_receipt),
        encoding="utf-8",
    )
    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="receipt_contract_invalid",
    ):
        current_support.verify_current_support_bundle(
            receipt_path=tampered_receipt_path,
            expected_source_sha=str(identity["commit_sha"]),
        )

    split_receipt = json.loads(
        (output_root / current_support.RECEIPT_NAME).read_text(encoding="utf-8")
    )
    split_receipt["support_bundle"]["bundle_index"] = current_support._file_row(
        Path(split_receipt["support_bundle"]["manifest"]["path"])
    )
    split_receipt["artifact_hash"] = current_support._artifact_hash(split_receipt)
    split_receipt_path = output_root / "split-manifest-receipt.json"
    split_receipt_path.write_text(json.dumps(split_receipt), encoding="utf-8")
    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="receipt_contract_invalid",
    ):
        current_support.verify_current_support_bundle(
            receipt_path=split_receipt_path,
            expected_source_sha=str(identity["commit_sha"]),
        )

    p0_path = Path(payload["generated_inputs"]["p0_status"]["path"])
    p0 = json.loads(p0_path.read_text(encoding="utf-8"))
    p0["status"] = "closed" if p0.get("status") == "open" else "open"
    p0_path.write_text(json.dumps(p0), encoding="utf-8")
    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="artifact_binding_invalid",
    ):
        current_support.verify_current_support_bundle(
            receipt_path=output_root / current_support.RECEIPT_NAME,
            expected_source_sha=str(identity["commit_sha"]),
        )


def test_current_builder_rejects_a_dirty_source_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _source_identity()
    identity["worktree_clean"] = False
    monkeypatch.setattr(current_support, "_git_identity", lambda: identity)
    monkeypatch.chdir(ROOT)
    output_root = tmp_path / "must-not-exist"

    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="source_worktree_not_clean",
    ):
        current_support.build_current_support_bundle(output_root=output_root)
    assert not output_root.exists()


def test_transitive_verifier_rejects_hash_coherent_unredacted_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    output_root = tmp_path / "redaction-attack"
    payload = current_support.build_current_support_bundle(
        output_root=output_root,
        expected_source_sha=str(identity["commit_sha"]),
    )
    manifest = json.loads(
        Path(payload["support_bundle"]["manifest"]["path"]).read_text(encoding="utf-8")
    )
    row = next(
        item
        for item in manifest["artifact_rows"]
        if Path(item["source_path"]).read_bytes()
        != Path(item["redacted_bundle_path"]).read_bytes()
    )
    source = Path(row["source_path"])
    redacted = Path(row["redacted_bundle_path"])
    redacted.write_bytes(source.read_bytes())
    row["redacted_sha256"] = current_support._plain_sha256(redacted)

    index_path = Path(manifest["bundle_index"]["path"])
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["artifact_rows"] = manifest["artifact_rows"]
    current_support._write_json(index_path, index)
    manifest["bundle_index"]["sha256"] = current_support._plain_sha256(index_path)

    archive_path = Path(manifest["export_archive"]["path"])
    bundle_dir = index_path.parent
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for member in manifest["export_archive"]["members"]:
            info = zipfile.ZipInfo(member)
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (bundle_dir / member).read_bytes())
    manifest["export_archive"]["bytes"] = archive_path.stat().st_size
    manifest["export_archive"]["sha256"] = current_support._plain_sha256(archive_path)

    generated_paths = {
        label: Path(payload["generated_inputs"][label]["path"])
        for label in current_support.GENERATED_INPUT_LABELS
    }
    assert not current_support._bundle_transitive_bindings_pass(
        support_bundle=manifest,
        generated_paths=generated_paths,
    )


def test_current_support_workflow_is_main_only_exact_source_and_bounded() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "current-support-bundle.yml"
    ).read_text(encoding="utf-8")

    assert 'branches: ["main"]' in workflow
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert 'test "$SOURCE_SHA" = "$WORKFLOW_SHA"' in workflow
    assert '--expected-source-sha "$SOURCE_SHA"' in workflow
    assert "scripts/build_current_support_bundle.py verify" in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "--deny-self-hosted-runners" in workflow
    assert "not product code signing" in workflow
    assert "human usability evidence" in workflow
    assert workflow.count("GH_TOKEN: ${{ github.token }}") == 1
    workflow_header, provenance_step = workflow.split(
        "- name: Retain and verify exact provenance bundle", maxsplit=1
    )
    assert "GH_TOKEN:" not in workflow_header
    assert "GH_TOKEN: ${{ github.token }}" in provenance_step
