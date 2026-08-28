from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import textwrap
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

    build_job, attest_job = workflow.split("\n  attest:\n", maxsplit=1)
    assert "build-verify-unprivileged" in build_job
    assert "id-token: write" not in build_job
    assert "attestations: write" not in build_job
    assert "artifact-metadata: write" not in build_job
    assert "needs: build-verify" in attest_job
    attest_header = attest_job.split("    runs-on:", maxsplit=1)[0]
    assert (
        "    permissions:\n"
        "      contents: read\n"
        "      id-token: write\n"
        "      attestations: write\n"
        "      artifact-metadata: write\n"
    ) in attest_header
    assert attest_header.count(": write") == 3
    assert (
        "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131"
        in attest_job
    )
    assert "artifact-ids: ${{ needs.build-verify.outputs.handoff-artifact-id }}" in (
        attest_job
    )
    assert "handoff-artifact-digest" in attest_job
    assert "github.run_id" in build_job
    assert "github.run_attempt" in build_job
    assert "id: handoff" in build_job
    assert "actions/checkout@" not in attest_job
    assert "actions/setup-python@" not in attest_job
    assert "pip install" not in attest_job
    assert "python scripts/" not in attest_job
    assert "python -I - \\" in attest_job
    assert '"$RECEIPT" \\' in attest_job
    assert '"$GITHUB_WORKFLOW_REF" \\' in attest_job
    assert (
        "Verify receipt hash and source identity without repository code" in attest_job
    )


def test_privileged_inline_verifier_rejects_minimal_hash_coherent_forgery(
    tmp_path: Path,
) -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "current-support-bundle.yml"
    ).read_text(encoding="utf-8")
    marker = "\"$HANDOFF_ARTIFACT_DIGEST\" <<'PY'\n"
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
            "sha256:" + "3" * 64,
        ],
        cwd=tmp_path,
        input=verifier,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "receipt_keys_invalid" in result.stderr
