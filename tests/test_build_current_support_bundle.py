from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import threading
from urllib.parse import urlsplit
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
    monkeypatch.setattr(current_support.frontend_audit, "git_identity", lambda: identity)
    monkeypatch.setattr(
        current_support,
        "_head_fixture_files",
        lambda _fixture: [fixture_file],
    )
    audit_payload = {
        "auditReportVersion": 2,
        "vulnerabilities": {},
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 0,
                "critical": 0,
                "total": 0,
            },
            "dependencies": {
                "prod": 11,
                "dev": 58,
                "optional": 34,
                "peer": 0,
                "peerOptional": 0,
                "total": 68,
            },
        },
    }
    monkeypatch.setattr(
        current_support.frontend_audit,
        "run_audit",
        lambda **_kwargs: {
            "payload": audit_payload,
            "exit_code": 0,
            "stdout": json.dumps(audit_payload),
            "signatures_payload": {"invalid": [], "missing": []},
            "signatures_exit_code": 0,
            "signatures_stdout": '{"invalid": [], "missing": []}',
            "node_version": "v24.20.0",
            "npm_version": "11.19.0",
            "effective_registry": "https://registry.npmjs.org/",
            "effective_strict_ssl": "true",
            "config_isolation": True,
        },
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


def test_current_builder_closes_54_of_54_without_promoting_child_statuses(
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
    assert payload["support_bundle"]["artifact_count"] == 54
    assert payload["support_bundle"]["available_artifact_count"] == 54
    assert payload["support_bundle"]["missing_required_count"] == 0
    assert all(payload["checks"].values())
    assert set(payload["generated_inputs"]) == set(
        current_support.GENERATED_INPUT_LABELS
    )
    frontend_audit_path = Path(
        payload["generated_inputs"]["frontend_dependency_audit_report"]["path"]
    )
    frontend_audit = json.loads(frontend_audit_path.read_text(encoding="utf-8"))
    assert frontend_audit["source"]["commit_sha"] == identity["commit_sha"]
    assert frontend_audit["source"]["tree_sha"] == identity["tree_sha"]
    assert frontend_audit["summary"]["vulnerability_total"] == 0
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
    frontend_row = next(
        row
        for row in manifest["artifact_rows"]
        if row["label"] == "frontend_dependency_audit_report"
    )
    assert Path(frontend_row["source_path"]) == frontend_audit_path
    generated_paths = {
        label: Path(payload["generated_inputs"][label]["path"])
        for label in current_support.GENERATED_INPUT_LABELS
    }
    for mutation in (
        lambda value: value.update(schema_version="forged"),
        lambda value: value.update(
            contract_pass=False,
            reason_code="ERR_SUPPORT_BUNDLE_EVIDENCE_PENDING",
            blockers=["forged"],
        ),
        lambda value: value["required_sections"].pop("p0_status"),
        lambda value: value["optional_sections"].update(forged="missing"),
    ):
        forged_manifest = json.loads(json.dumps(manifest))
        mutation(forged_manifest)
        assert not current_support._support_manifest_semantics_pass(
            support_bundle=forged_manifest,
            generated_paths=generated_paths,
        )

    transplanted_manifest = json.loads(json.dumps(manifest))
    rows_by_label = {
        row["label"]: row for row in transplanted_manifest["artifact_rows"]
    }
    first_label = "runtime_probe"
    second_label = "runtime_packaging_manifest"
    first_row = rows_by_label[first_label]
    second_row = rows_by_label[second_label]
    first_values = {key: value for key, value in first_row.items() if key != "label"}
    second_values = {key: value for key, value in second_row.items() if key != "label"}
    first_row.update(second_values)
    first_row["label"] = first_label
    second_row.update(first_values)
    second_row["label"] = second_label
    transplanted_manifest["required_sections"][first_label] = first_row[
        "redacted_bundle_path"
    ]
    transplanted_manifest["required_sections"][second_label] = second_row[
        "redacted_bundle_path"
    ]
    assert not current_support._support_manifest_semantics_pass(
        support_bundle=transplanted_manifest,
        generated_paths=generated_paths,
    )
    assert not current_support._bundle_transitive_bindings_pass(
        support_bundle=transplanted_manifest,
        generated_paths=generated_paths,
    )

    absolute_alias_manifest = json.loads(json.dumps(manifest))
    aliased_source_row = next(
        row
        for row in absolute_alias_manifest["artifact_rows"]
        if row["label"] == "runtime_probe"
    )
    aliased_source_row["source_path"] = str(
        (ROOT / aliased_source_row["source_path"]).resolve()
    )
    assert not current_support._support_manifest_semantics_pass(
        support_bundle=absolute_alias_manifest,
        generated_paths=generated_paths,
    )

    redacted_alias_manifest = json.loads(json.dumps(manifest))
    aliased_redacted_row = next(
        row
        for row in redacted_alias_manifest["artifact_rows"]
        if row["label"] == "runtime_probe"
    )
    canonical_redacted = Path(aliased_redacted_row["redacted_bundle_path"])
    aliased_redacted_row["redacted_bundle_path"] = str(
        canonical_redacted.parent / ".." / "redacted" / canonical_redacted.name
    )
    redacted_alias_manifest["required_sections"]["runtime_probe"] = (
        aliased_redacted_row["redacted_bundle_path"]
    )
    assert not current_support._support_manifest_semantics_pass(
        support_bundle=redacted_alias_manifest,
        generated_paths=generated_paths,
    )
    assert not current_support._bundle_transitive_bindings_pass(
        support_bundle=redacted_alias_manifest,
        generated_paths=generated_paths,
    )

    p0_payload = json.loads(
        Path(payload["generated_inputs"]["p0_status"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    malformed_p0 = json.loads(json.dumps(p0_payload))
    malformed_p0["gates"].append("scalar-forgery")
    assert not current_support._p0_status_coherent(malformed_p0)
    p1_payload = json.loads(
        Path(payload["generated_inputs"]["p1_status"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    malformed_p1 = json.loads(json.dumps(p1_payload))
    malformed_p1["gates"].append(7)
    assert not current_support._p1_status_coherent(
        malformed_p1,
        p0=p0_payload,
    )

    client_payload = json.loads(
        Path(
            payload["generated_inputs"]["client_input_validation_report"]["path"]
        ).read_text(encoding="utf-8")
    )
    forged_client = json.loads(json.dumps(client_payload))
    forged_client["claim_boundary"]["forbidden"] = []
    forged_client["artifact_hash"] = current_support._artifact_hash(forged_client)
    assert not current_support._client_report_semantics_pass(
        client_input=forged_client,
        fixture=current_support.DEFAULT_CLIENT_FIXTURE,
    )
    forged_binding = json.loads(json.dumps(client_payload))
    forged_binding["input_binding"]["current_worktree_bound"] = False
    forged_binding["artifact_hash"] = current_support._artifact_hash(forged_binding)
    assert not current_support._client_report_semantics_pass(
        client_input=forged_binding,
        fixture=current_support.DEFAULT_CLIENT_FIXTURE,
    )
    project_ops_payload = json.loads(
        Path(payload["generated_inputs"]["project_ops_snapshot"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    assert current_support._project_ops_producer_semantics_pass(
        project_ops=project_ops_payload,
        snapshot_path=generated_paths["project_ops_snapshot"],
    )
    forged_project_ops = json.loads(json.dumps(project_ops_payload))
    forged_project_ops["summary_line"] = "FORGED project-operations authority"
    forged_project_ops["release_authority"] = True
    assert not current_support._project_ops_producer_semantics_pass(
        project_ops=forged_project_ops,
        snapshot_path=generated_paths["project_ops_snapshot"],
    )
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

    for key, value in (
        ("release_authority", True),
        ("generated_at", True),
    ):
        malformed_receipt = json.loads(
            (output_root / current_support.RECEIPT_NAME).read_text(encoding="utf-8")
        )
        malformed_receipt[key] = value
        malformed_receipt["artifact_hash"] = current_support._artifact_hash(
            malformed_receipt
        )
        malformed_path = output_root / f"malformed-{key}.json"
        malformed_path.write_text(json.dumps(malformed_receipt), encoding="utf-8")
        with pytest.raises(
            current_support.CurrentSupportBundleError,
            match="receipt_schema_invalid",
        ):
            current_support.verify_current_support_bundle(
                receipt_path=malformed_path,
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


def test_source_containment_rejects_external_files_and_symlinks(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external.json"
    external.write_text("{}\n", encoding="utf-8")
    assert not current_support._contained_regular_file(
        external,
        root=ROOT,
    )

    generated_root = tmp_path / "generated"
    generated_root.mkdir()
    target = generated_root / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    link = generated_root / "source.json"
    link.symlink_to(target)
    assert not current_support._contained_regular_file(
        link,
        root=generated_root,
    )


def test_current_builder_rejects_a_symlinked_output_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="output_path_symlink_forbidden",
    ):
        current_support.build_current_support_bundle(
            output_root=alias_parent / "support-bundle",
            expected_source_sha=str(identity["commit_sha"]),
        )

    assert not (real_parent / "support-bundle").exists()

    nested_target = real_parent / "nested"
    nested_target.mkdir()
    escape_alias = tmp_path / "escape-alias"
    escape_alias.symlink_to(nested_target, target_is_directory=True)
    with pytest.raises(
        current_support.CurrentSupportBundleError,
        match="output_path_parent_traversal_forbidden",
    ):
        current_support.build_current_support_bundle(
            output_root=escape_alias / ".." / "escaped-support-bundle",
            expected_source_sha=str(identity["commit_sha"]),
        )

    assert not (real_parent / "escaped-support-bundle").exists()


def test_failed_staging_is_cleaned_and_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    output_root = tmp_path / "atomic-output"
    original = current_support.build_support_bundle

    def fail_once(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected staging failure")

    monkeypatch.setattr(current_support, "build_support_bundle", fail_once)
    with pytest.raises(RuntimeError, match="injected staging failure"):
        current_support.build_current_support_bundle(
            output_root=output_root,
            expected_source_sha=str(identity["commit_sha"]),
        )
    assert not output_root.exists()
    assert list(tmp_path.glob(".atomic-output.tmp-*")) == []

    monkeypatch.setattr(current_support, "build_support_bundle", original)
    payload = current_support.build_current_support_bundle(
        output_root=output_root,
        expected_source_sha=str(identity["commit_sha"]),
    )
    assert payload["contract_pass"] is True


def test_atomic_publish_observes_complete_staging_before_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    output_root = tmp_path / "atomic-visibility"
    original = current_support._atomic_publish
    observed: list[bool] = []

    def inspect_then_publish(staging: Path, final: Path) -> None:
        observed.append(
            not final.exists()
            and (staging / current_support.RECEIPT_NAME).is_file()
            and (staging / "support-bundle-export.zip").is_file()
        )
        original(staging, final)

    monkeypatch.setattr(current_support, "_atomic_publish", inspect_then_publish)
    payload = current_support.build_current_support_bundle(
        output_root=output_root,
        expected_source_sha=str(identity["commit_sha"]),
    )
    assert payload["contract_pass"] is True
    assert observed == [True]


def test_repo_contained_atomic_rebase_keeps_logical_paths_relative() -> None:
    staging = ROOT / ".ci" / ".current-support-bundle.tmp-test"
    final = ROOT / ".ci" / "current-support-bundle-test"

    rebased = current_support._rebase_value(
        {"path": str(staging / "generated" / "p0-status.json")},
        old_root=staging,
        new_root=current_support._display_path(final),
    )

    assert rebased == {
        "path": ".ci/current-support-bundle-test/generated/p0-status.json"
    }


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
    assert "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38" in workflow
    assert 'test "$(node --version)" = "v24.20.0"' in workflow
    assert 'test "$(npm --version)" = "11.19.0"' in workflow
    assert workflow.index("Capture isolated registry audit") < workflow.index(
        "Install hash-locked contract tools"
    )
    assert "exact-source support bundle and npm audit" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "--deny-self-hosted-runners" in workflow
    assert "not product code signing" in workflow
    assert "human usability evidence" in workflow
    assert workflow.count("GH_TOKEN: ${{ github.token }}") == 2
    workflow_header, provenance_step = workflow.split(
        "- name: Retain and verify exact provenance bundle", maxsplit=1
    )
    assert workflow_header.count("GH_TOKEN: ${{ github.token }}") == 1
    assert "GH_TOKEN: ${{ github.token }}" in provenance_step

    build_job, attest_job = workflow.split("\n  attest:\n", maxsplit=1)
    assert "build-verify-unprivileged" in build_job
    assert "    permissions:\n      contents: read\n" in build_job
    assert "actions: read" not in build_job
    assert "id-token: write" not in build_job
    assert "attestations: write" not in build_job
    assert "artifact-metadata: write" not in build_job
    assert "needs: build-verify" in attest_job
    attest_header = attest_job.split("    runs-on:", maxsplit=1)[0]
    assert (
        "    permissions:\n"
        "      actions: read\n"
        "      contents: read\n"
        "      id-token: write\n"
        "      attestations: write\n"
        "      artifact-metadata: write\n"
    ) in attest_header
    assert attest_header.count(": write") == 3
    assert "actions/download-artifact@" not in attest_job
    assert "/actions/artifacts/{artifact_id}/zip" in attest_job
    assert "/attempts/" in attest_job
    assert 'f"{run_attempt}/jobs?per_page=100"' in attest_job
    assert "github_api_redirect_forbidden" in attest_job
    assert "github_api_origin_or_path_changed" in attest_job
    assert "artifact_archive_api_origin_or_path_changed" in attest_job
    assert "artifact_storage_redirect_forbidden" in attest_job
    assert "artifact_storage_origin_or_path_changed" in attest_job
    assert "artifact_archive_member_allowlist_invalid" in attest_job
    assert "handoff-artifact-digest" in attest_job
    assert "github.run_id" in build_job
    assert "github.run_attempt" in build_job
    assert "id: handoff" in build_job
    assert (
        "name: current-support-bundle-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ env.SOURCE_SHA }}"
    ) in attest_job
    assert "actions/checkout@" not in attest_job
    assert "actions/setup-python@" not in attest_job
    assert "actions/setup-node@" not in attest_job
    assert "pip install" not in attest_job
    assert "python scripts/" not in attest_job
    assert "run: npm " not in attest_job
    assert "python -I - \\" in attest_job
    assert '"$RECEIPT" \\' in attest_job
    assert '"$GITHUB_WORKFLOW_REF" \\' in attest_job
    assert (
        "Download and verify exact handoff without repository code" in attest_job
    )


def test_privileged_inline_verifier_rejects_minimal_hash_coherent_forgery(
    tmp_path: Path,
) -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "current-support-bundle.yml"
    ).read_text(encoding="utf-8")
    marker = "\"$GITHUB_API_URL\" <<'PY'\n"
    script_start = workflow.index(marker) + len(marker)
    script_end = workflow.index("\n          PY", script_start)
    verifier = textwrap.dedent(workflow[script_start:script_end])

    output_root = tmp_path / ".ci" / "current-support-bundle"
    output_root.mkdir(parents=True)
    source_sha = "1" * 40
    forged = {
        "schema_version": "current-support-bundle-receipt.v1",
        "source": {
            "commit_sha": source_sha,
            "expected_commit_sha": source_sha,
            "tree_sha": "2" * 40,
            "worktree_clean": True,
        },
        "output_root": ".ci/current-support-bundle",
        "contract_pass": True,
        "reason_code": "PASS",
        "blockers": [],
        "checks": {"forged": True},
    }
    forged["artifact_hash"] = current_support._artifact_hash(forged)
    receipt = output_root / current_support.RECEIPT_NAME
    receipt.write_text(json.dumps(forged), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            ".ci/current-support-bundle/current-support-bundle-receipt.v1.json",
            source_sha,
            source_sha,
            ".ci/current-support-bundle",
            "owner/repository",
            (
                "owner/repository/.github/workflows/"
                "current-support-bundle.yml@refs/heads/main"
            ),
            "refs/heads/main",
            "1",
            "3" * 64,
            "123",
            "1",
            "http://127.0.0.1:1",
        ],
        cwd=tmp_path,
        input=verifier,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0


def test_privileged_inline_verifier_replays_full_handoff_and_rejects_attacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _prepare_source_mocks(monkeypatch)
    output_root = tmp_path / "current-support-bundle"
    payload = current_support.build_current_support_bundle(
        output_root=output_root,
        expected_source_sha=str(identity["commit_sha"]),
    )
    workflow = (
        ROOT / ".github" / "workflows" / "current-support-bundle.yml"
    ).read_text(encoding="utf-8")
    marker = "\"$GITHUB_API_URL\" <<'PY'\n"
    script_start = workflow.index(marker) + len(marker)
    script_end = workflow.index("\n          PY", script_start)
    verifier = textwrap.dedent(workflow[script_start:script_end])
    source_sha = str(identity["commit_sha"])
    tree_sha = str(identity["tree_sha"])
    artifact_id = "456"
    run_id = "123"
    run_attempt = "1"

    p0_payload = json.loads(
        Path(payload["generated_inputs"]["p0_status"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    p1_payload = json.loads(
        Path(payload["generated_inputs"]["p1_status"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    repository_paths = {
        path.as_posix()
        for path in current_support.SUPPORT_DEFAULT_SOURCE_PATHS.values()
    }
    repository_paths.update(
        path
        for path, digest in {
            **p0_payload["input_checksums"],
            **p1_payload["input_checksums"],
        }.items()
        if digest != "missing" and not Path(path).is_absolute()
    )
    repository_paths.update(
        {
            "scripts/validate_client_input_package.py",
            (
                "src/structural_analysis/schemas/"
                "client_input_validation_report_v1.schema.json"
            ),
            "tests/fixtures/current_support_bundle/client_input/model.json",
        }
    )
    source_bytes = {
        path: (ROOT / path).read_bytes()
        for path in repository_paths
        if (ROOT / path).is_file()
    }
    tree_rows = []
    blobs: dict[str, bytes] = {}
    for path, raw_bytes in sorted(source_bytes.items()):
        blob_sha = hashlib.sha256(path.encode("utf-8") + raw_bytes).hexdigest()[:40]
        blobs[blob_sha] = raw_bytes
        tree_rows.append(
            {
                "path": path,
                "type": "blob",
                "sha": blob_sha,
                "size": len(raw_bytes),
            }
        )

    receipt_path = output_root / current_support.RECEIPT_NAME
    original_files = {
        path: path.read_bytes() for path in output_root.rglob("*") if path.is_file()
    }

    def make_archive() -> bytes:
        stream = BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(row for row in output_root.rglob("*") if row.is_file()):
                info = zipfile.ZipInfo(path.relative_to(output_root).as_posix())
                info.date_time = (2026, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        return stream.getvalue()

    state: dict[str, object] = {
        "archive": b"",
        "artifact_id": artifact_id,
        "artifact_digest": "",
        "jobs_present": True,
        "metadata_redirect": False,
    }

    credential_sink: dict[str, object] = {
        "requests": 0,
        "authorization": [],
    }

    class CredentialSinkHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            credential_sink["requests"] = int(credential_sink["requests"]) + 1
            authorization = credential_sink["authorization"]
            assert isinstance(authorization, list)
            authorization.append(self.headers.get("Authorization"))
            encoded = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    sink_server = ThreadingHTTPServer(("127.0.0.1", 0), CredentialSinkHandler)
    sink_thread = threading.Thread(target=sink_server.serve_forever, daemon=True)
    sink_thread.start()
    sink_url = f"http://127.0.0.1:{sink_server.server_port}/credential-sink"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path.endswith(f"/git/commits/{source_sha}"):
                response = {"sha": source_sha, "tree": {"sha": tree_sha}}
            elif path.endswith(
                f"/actions/runs/{run_id}/attempts/{run_attempt}/jobs"
            ):
                jobs = (
                    [
                        {
                            "id": 789,
                            "run_id": int(run_id),
                            "run_attempt": int(run_attempt),
                            "head_sha": source_sha,
                            "name": "build-verify-unprivileged",
                            "status": "completed",
                            "conclusion": "success",
                            "completed_at": "2026-08-28T00:00:00+00:00",
                        }
                    ]
                    if state["jobs_present"]
                    else []
                )
                response = {"total_count": len(jobs), "jobs": jobs}
            elif path.endswith(f"/actions/runs/{run_id}/attempts/{run_attempt}"):
                response = {
                    "id": int(run_id),
                    "run_attempt": int(run_attempt),
                    "head_sha": source_sha,
                    "path": ".github/workflows/current-support-bundle.yml",
                }
            elif path.endswith(f"/actions/artifacts/{state['artifact_id']}/zip"):
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://127.0.0.1:{self.server.server_port}/artifact-download",
                )
                self.end_headers()
                return
            elif path == "/artifact-download":
                archive_bytes = state["archive"]
                assert isinstance(archive_bytes, bytes)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(archive_bytes)))
                self.end_headers()
                self.wfile.write(archive_bytes)
                return
            elif path.endswith(f"/actions/artifacts/{state['artifact_id']}"):
                if state["metadata_redirect"]:
                    self.send_response(302)
                    self.send_header("Location", sink_url)
                    self.end_headers()
                    return
                response = {
                    "id": int(str(state["artifact_id"])),
                    "name": (
                        "current-support-bundle-handoff-"
                        f"{run_id}-{run_attempt}-{source_sha}"
                    ),
                    "digest": f"sha256:{state['artifact_digest']}",
                    "expired": False,
                    "size_in_bytes": len(state["archive"]),
                    "workflow_run": {"id": int(run_id), "head_sha": source_sha},
                }
            elif path.endswith(f"/git/trees/{tree_sha}"):
                response = {
                    "sha": tree_sha,
                    "truncated": False,
                    "tree": tree_rows,
                }
            elif "/git/blobs/" in path:
                blob_sha = path.rsplit("/", maxsplit=1)[-1]
                raw_bytes = blobs[blob_sha]
                response = {
                    "sha": blob_sha,
                    "encoding": "base64",
                    "content": base64.b64encode(raw_bytes).decode("ascii"),
                }
            else:
                self.send_error(404)
                return
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_url = f"http://127.0.0.1:{server.server_port}"

    def restore() -> None:
        if output_root.exists():
            shutil.rmtree(output_root)
        for path, raw_bytes in original_files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw_bytes)

    def run_inline(
        *,
        selected_artifact_id: str = artifact_id,
        selected_artifact_digest: str | None = None,
        jobs_present: bool = True,
        metadata_redirect: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        archive_bytes = make_archive()
        actual_digest = hashlib.sha256(archive_bytes).hexdigest()
        chosen_digest = selected_artifact_digest or actual_digest
        state.update(
            {
                "archive": archive_bytes,
                "artifact_id": selected_artifact_id,
                "artifact_digest": chosen_digest,
                "jobs_present": jobs_present,
                "metadata_redirect": metadata_redirect,
            }
        )
        shutil.rmtree(output_root)
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-",
                str(receipt_path),
                source_sha,
                source_sha,
                str(output_root),
                "owner/repository",
                (
                    "owner/repository/.github/workflows/"
                    "current-support-bundle.yml@refs/heads/main"
                ),
                "refs/heads/main",
                selected_artifact_id,
                chosen_digest,
                run_id,
                run_attempt,
                api_url,
            ],
            cwd=ROOT,
            input=verifier,
            text=True,
            capture_output=True,
            check=False,
            env={"GH_TOKEN": "offline-test-token"},
        )

    def bind_receipt_file(section: str, label: str, path: Path) -> None:
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_payload[section][label] = current_support._file_row(path)
        receipt_payload["artifact_hash"] = current_support._artifact_hash(
            receipt_payload
        )
        receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")

    try:
        valid = run_inline()
        assert valid.returncode == 0, valid.stderr

        smuggled = output_root / "release-approved.json"
        smuggled.write_text('{"release_authority": true}\n', encoding="utf-8")
        smuggled_output = run_inline()
        assert smuggled_output.returncode != 0
        assert "output_file_allowlist_invalid" in smuggled_output.stderr
        smuggled.unlink()

        client_path = Path(
            payload["generated_inputs"]["client_input_validation_report"]["path"]
        )
        client_payload = json.loads(client_path.read_text(encoding="utf-8"))
        client_payload["checks"] = {"forged": True}
        client_payload["data_file_checks"] = [False]
        client_payload["input_binding"]["file_count"] = True
        client_payload["artifact_hash"] = current_support._artifact_hash(client_payload)
        client_path.write_text(json.dumps(client_payload), encoding="utf-8")
        bind_receipt_file(
            "generated_inputs",
            "client_input_validation_report",
            client_path,
        )
        forged_client_semantics = run_inline()
        assert forged_client_semantics.returncode != 0
        assert "client_payload_contract_invalid" in forged_client_semantics.stderr

        restore()
        p0_path = Path(payload["generated_inputs"]["p0_status"]["path"])
        p0_payload = json.loads(p0_path.read_text(encoding="utf-8"))
        release_gate = next(
            gate
            for gate in p0_payload["gates"]
            if gate["label"] == "P0-1 release publication"
        )
        release_gate["ok"] = True
        release_gate["status"] = "closed"
        p0_payload["release_publication_closed"] = True
        p0_payload["p0_closed"] = True
        p0_payload["status"] = "closed"
        p0_path.write_text(json.dumps(p0_payload), encoding="utf-8")
        bind_receipt_file("generated_inputs", "p0_status", p0_path)
        forged_p0_authority = run_inline()
        assert forged_p0_authority.returncode != 0
        assert "p0_current_non_authority_boundary_invalid" in forged_p0_authority.stderr

        restore()
        project_path = Path(payload["generated_inputs"]["project_ops_snapshot"]["path"])
        project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        project_payload["projects"] = [{}]
        project_payload["project_rows"] = [{}]
        project_payload["health"]["checks"] = {
            key: True for key in project_payload["health"]["checks"]
        }
        project_payload["health"]["missing_inputs"] = []
        project_payload["health"]["status"] = "ok"
        project_payload["contract_pass"] = True
        project_payload["reason_code"] = "PASS"
        project_payload["reason"] = "project ops service snapshot generated"
        project_path.write_text(json.dumps(project_payload), encoding="utf-8")
        bind_receipt_file("generated_inputs", "project_ops_snapshot", project_path)
        forged_project_authority = run_inline()
        assert forged_project_authority.returncode != 0
        assert (
            "project_ops_current_non_authority_boundary_invalid"
            in forged_project_authority.stderr
        )

        restore()
        project_path = Path(payload["generated_inputs"]["project_ops_snapshot"]["path"])
        project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        project_payload["release_authority"] = True
        project_path.write_text(json.dumps(project_payload), encoding="utf-8")
        bind_receipt_file("generated_inputs", "project_ops_snapshot", project_path)
        forged_project = run_inline()
        assert forged_project.returncode != 0
        assert "project_ops_payload_shape_invalid" in forged_project.stderr

        restore()
        frontend_path = Path(
            payload["generated_inputs"]["frontend_dependency_audit_report"]["path"]
        )
        frontend_payload = json.loads(frontend_path.read_text(encoding="utf-8"))
        frontend_payload["source"]["tree_sha"] = "4" * 40
        frontend_payload["artifact_hash"] = current_support._canonical_hash(
            {
                key: value
                for key, value in frontend_payload.items()
                if key != "artifact_hash"
            }
        )
        frontend_path.write_text(json.dumps(frontend_payload), encoding="utf-8")
        bind_receipt_file(
            "generated_inputs",
            "frontend_dependency_audit_report",
            frontend_path,
        )
        forged_frontend = run_inline()
        assert forged_frontend.returncode != 0
        assert (
            "generated_support_binding_invalid:frontend_dependency_audit_report"
            in forged_frontend.stderr
        )

        restore()
        manifest_path = Path(payload["support_bundle"]["manifest"]["path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = {row["label"]: row for row in manifest["artifact_rows"]}
        (
            rows["runtime_probe"]["source_path"],
            rows["runtime_packaging_manifest"]["source_path"],
        ) = (
            rows["runtime_packaging_manifest"]["source_path"],
            rows["runtime_probe"]["source_path"],
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        bind_receipt_file("support_bundle", "manifest", manifest_path)
        transplanted = run_inline()
        assert transplanted.returncode != 0
        assert "support_row_invalid:runtime_probe" in transplanted.stderr

        restore()
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_payload["source"]["tree_sha"] = "4" * 40
        receipt_payload["artifact_hash"] = current_support._artifact_hash(
            receipt_payload
        )
        receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
        fake_tree = run_inline()
        assert fake_tree.returncode != 0
        assert "github_commit_tree_binding_invalid" in fake_tree.stderr

        restore()
        missing_jobs = run_inline(jobs_present=False)
        assert missing_jobs.returncode != 0
        assert "github_build_job_identity_invalid" in missing_jobs.stderr

        restore()
        redirected_metadata = run_inline(metadata_redirect=True)
        assert redirected_metadata.returncode != 0
        assert "github_api_redirect_forbidden" in redirected_metadata.stderr
        assert credential_sink["requests"] == 0
        assert credential_sink["authorization"] == []

        restore()
        fake_artifact = run_inline(
            selected_artifact_id="999",
            selected_artifact_digest="5" * 64,
        )
        assert fake_artifact.returncode != 0
        assert "artifact_archive_byte_binding_invalid" in fake_artifact.stderr
    finally:
        server.shutdown()
        thread.join(timeout=5)
        sink_server.shutdown()
        sink_thread.join(timeout=5)
