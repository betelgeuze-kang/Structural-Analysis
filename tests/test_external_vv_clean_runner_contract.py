"""Tests for the same-operator container-isolated external V&V candidate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "benchmarks/clean-runners/opensees-calculix"
RUNNER = PACKAGE / "run_clean_runner.py"
DOCKERFILE = PACKAGE / "Dockerfile"
OUTPUT = ROOT / "artifacts/vv/opensees_calculix_clean_runner"
SUMMARY = OUTPUT / "clean_runner_receipt.json"
CODE_RECEIPT = OUTPUT / "external_code_to_code_receipt.json"
MODAL_RECEIPT = OUTPUT / "external_modal_buckling_receipt.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module("external_vv_clean_runner", RUNNER)
code_module = _load_module(
    "external_vv_code_receipt",
    ROOT / "scripts/run_external_code_to_code_technical_receipt.py",
)
modal_module = _load_module(
    "external_vv_modal_receipt",
    ROOT / "scripts/run_external_modal_buckling_technical_receipt.py",
)


def _json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _materialize_summary_evidence(
    evidence_root: Path, payload: dict
) -> None:
    paths = [
        *(Path(row["path"]) for row in payload["product_receipts"].values()),
        *(
            Path(row["path"])
            for row in payload["cross_environment_parity"][
                "host_reference_receipts"
            ].values()
        ),
    ]
    for relative in paths:
        target = evidence_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def _is_ancestor(ancestor: str, descendant: str, *, cwd: Path = ROOT) -> bool:
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return True
    if probe.returncode != 1:
        raise AssertionError(
            "git merge-base ancestry probe failed: "
            f"returncode={probe.returncode} stderr={probe.stderr.strip()!r}"
        )

    # Walk raw commit objects rather than another revision walker. Both
    # merge-base and rev-list honor a transient .git/shallow boundary even
    # when every parent object is still available. Raw parent links retain
    # the cryptographic ancestry while missing or malformed objects fail
    # closed.
    pending = [descendant]
    visited: set[str] = set()
    while pending:
        commit = pending.pop()
        if commit in visited:
            continue
        visited.add(commit)

        with subprocess.Popen(
            ["git", "cat-file", "-p", commit],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as reader:
            stdout, stderr = reader.communicate()
        if reader.returncode != 0:
            raise AssertionError(
                "git cat-file ancestry fallback failed: "
                f"commit={commit} returncode={reader.returncode} "
                f"stderr={stderr.strip()!r}"
            )

        header, separator, _ = stdout.partition("\n\n")
        if not separator:
            raise AssertionError(
                f"git commit object has no header terminator: commit={commit}"
            )
        header_lines = header.splitlines()
        if not header_lines or not re.fullmatch(
            r"tree [0-9a-f]{40}", header_lines[0]
        ):
            raise AssertionError(
                f"git commit object has invalid tree header: commit={commit}"
            )
        if commit == ancestor:
            return True
        for line in header_lines[1:]:
            if not line.startswith("parent "):
                continue
            parent = line.removeprefix("parent ")
            if not re.fullmatch(r"[0-9a-f]{40}", parent):
                raise AssertionError(
                    f"git commit object has invalid parent: commit={commit}"
                )
            pending.append(parent)
    return False


def test_git_ancestry_fallback_walks_raw_objects_across_shallow_boundary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT
        ).strip()

    git("init", "-q", "--initial-branch=main")
    git("config", "user.email", "ci@example.invalid")
    git("config", "user.name", "CI")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    git("add", "root.txt")
    git("commit", "-q", "-m", "root")
    root = git("rev-parse", "HEAD")

    (repo / "intermediate.txt").write_text("intermediate\n", encoding="utf-8")
    git("add", "intermediate.txt")
    git("commit", "-q", "-m", "intermediate")
    intermediate = git("rev-parse", "HEAD")

    (repo / "descendant.txt").write_text("descendant\n", encoding="utf-8")
    git("add", "descendant.txt")
    git("commit", "-q", "-m", "descendant")
    descendant = git("rev-parse", "HEAD")

    git("switch", "-q", "--detach", root)
    (repo / "sibling.txt").write_text("sibling\n", encoding="utf-8")
    git("add", "sibling.txt")
    git("commit", "-q", "-m", "sibling")
    sibling = git("rev-parse", "HEAD")

    git_dir = Path(git("rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    (git_dir / "shallow").write_text(f"{intermediate}\n", encoding="ascii")

    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", root, descendant],
            cwd=repo,
            check=False,
        ).returncode
        == 1
    )
    assert root not in git("rev-list", descendant).splitlines()
    assert f"parent {root}" in git("cat-file", "-p", intermediate).splitlines()

    assert _is_ancestor(root, descendant, cwd=repo)
    assert not _is_ancestor(sibling, descendant, cwd=repo)


def test_git_ancestry_probe_preserves_git_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def git_error(command, **kwargs):
        return subprocess.CompletedProcess(command, 128, "", "fatal: corrupt graph")

    monkeypatch.setattr(subprocess, "run", git_error)

    with pytest.raises(AssertionError, match="fatal: corrupt graph"):
        _is_ancestor("0" * 40, "1" * 40, cwd=tmp_path)


def test_external_receipt_documents_do_not_copy_volatile_replay_hashes() -> None:
    document = (
        ROOT / "docs/external-code-to-code-technical-execution.md"
    ).read_text(encoding="utf-8")
    ledger = (
        ROOT / "docs/commercial-structural-solver-product-gap-ledger.md"
    ).read_text(encoding="utf-8")

    assert "volatile replay hash를 문서에 복제하지 않는다" in document
    assert "volatile replay hash를 복제하지 않는다" in ledger
    assert not re.search(r"현재 receipt artifact hash는\s*`sha256:", document)
    assert not re.search(r"현재 artifact hash는\s*`sha256:", document)
    assert not re.search(r"summary artifact hash는\s*`sha256:", document)
    assert not re.search(
        r"(?:Current-product replay artifact hash는|"
        r"current-product replay artifact hash|Summary artifact hash는)\s*"
        r"`sha256:",
        ledger,
    )


def test_tracked_clean_runner_summary_is_historical_schema_valid_and_nonpromoting() -> None:
    payload = _json(SUMMARY)
    schema = _json(ROOT / runner.SCHEMA_RELATIVE_PATH)
    readme = (OUTPUT / "README.md").read_text(encoding="utf-8")

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert "historical output" in readme
    assert "never current-main authority" in readme
    assert "does not fall back to this" in readme
    assert "tracked snapshot" in readme

    assert payload["status"] == "partial"
    assert payload["technical_contract_pass"] is True
    assert payload["isolation"] == {
        "repository_mount_read_only": True,
        "runtime_default_network_route_present": False,
        "designated_output_mount_writable": True,
        "isolation_contract_pass": True,
    }
    assert payload["runner"]["base_image"] == runner.BASE_IMAGE
    assert payload["external_assets"] == [
        {
            "filename": name,
            "sha256": "sha256:" + runner.ASSET_POLICY[name],
            "bundled_in_repository": False,
        }
        for name in sorted(runner.ASSET_POLICY)
    ]
    fresh_execution = all(
        descriptor["fresh_external_runtime_execution"] is True
        for descriptor in payload["product_receipts"].values()
    )
    assert payload["claims"]["same_operator_container_isolated_reproduction"] is (
        fresh_execution
    )
    assert payload["claims"]["actual_external_solver_execution"] is True
    for forbidden in (
        "independent_operator_attestation",
        "product_legal_license_approval",
        "external_runtime_redistribution_approval",
        "verification_level_2",
        "commercial_equivalence",
        "design_authority",
        "release_readiness",
    ):
        assert payload["claims"][forbidden] is False
    assert "independent_operator_attestation_missing" in payload["blockers_remaining"]
    assert (
        runner.REUSED_EXECUTION_BLOCKER in payload["blockers_remaining"]
    ) is (not fresh_execution)
    parity = payload["cross_environment_parity"]
    assert payload["claims"]["cross_environment_numerical_parity"] is parity[
        "numerical_contract_pass"
    ]
    assert (
        runner.CROSS_ENVIRONMENT_PARITY_BLOCKER
        in payload["blockers_remaining"]
    ) is (not parity["numerical_contract_pass"])


def test_summary_schema_allows_only_the_named_host_replays() -> None:
    payload = deepcopy(_json(SUMMARY))
    schema = _json(ROOT / runner.SCHEMA_RELATIVE_PATH)
    host_receipts = payload["cross_environment_parity"][
        "host_reference_receipts"
    ]
    host_receipts["code_to_code"]["path"] = (
        "artifacts/vv/opensees_calculix_clean_runner/"
        "host_external_code_to_code_current_source_replay.json"
    )
    host_receipts["modal_buckling"]["path"] = (
        "artifacts/vv/opensees_calculix_clean_runner/"
        "host_external_modal_buckling_current_source_replay.json"
    )

    validator = Draft202012Validator(schema)
    validator.validate(payload)

    host_receipts["code_to_code"]["path"] = (
        "artifacts/vv/opensees_calculix_clean_runner/untrusted.json"
    )
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_embedded_product_receipts_preserve_integrity_and_invalidate_stale_sources() -> None:
    summary = _json(SUMMARY)
    code = _json(CODE_RECEIPT)
    modal = _json(MODAL_RECEIPT)

    for receipt, validator, current_checksums, error_type in (
        (
            code,
            code_module.validate_external_code_to_code_technical_receipt,
            code_module._source_checksums(ROOT),
            code_module.ExternalCodeToCodeReceiptError,
        ),
        (
            modal,
            modal_module.validate_external_modal_buckling_technical_receipt,
            modal_module._source_checksums(ROOT),
            modal_module.ExternalModalBucklingReceiptError,
        ),
    ):
        validator(receipt, repo_root=ROOT, require_current_sources=False)
        source_is_current = (
            receipt["internal_source"]["input_checksums"] == current_checksums
        )
        if source_is_current:
            validator(receipt, repo_root=ROOT, require_current_sources=True)
        else:
            with pytest.raises(error_type, match="receipt_sources_stale"):
                validator(receipt, repo_root=ROOT, require_current_sources=True)
            assert (
                "external_runtime_current_source_rerun_missing"
                in receipt["blockers_remaining"]
            )

    for name, receipt, path in (
        ("code_to_code", code, CODE_RECEIPT),
        ("modal_buckling", modal, MODAL_RECEIPT),
    ):
        descriptor = summary["product_receipts"][name]
        assert descriptor["file_sha256"] == runner._file_hash(path)
        assert descriptor["artifact_hash"] == receipt["artifact_hash"]
        assert (
            descriptor["source_set_hash"]
            == receipt["internal_source"]["source_set_hash"]
        )
        assert descriptor["technical_contract_pass"] is True
        replay = receipt["replay_provenance"]
        fresh_execution = (
            replay["external_runtime_executed_in_this_generation"] is True
            and replay["external_execution_reused"] is False
        )
        assert descriptor["fresh_external_runtime_execution"] is fresh_execution
        assert receipt["claims"]["verification_level_2"] is False

    assert code["claims"][
        "public_corotational_portal_technical_comparison"
    ] is True

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    recorded_commits = {
        summary["source_commit_sha"],
        code["source_commit_sha"],
        modal["source_commit_sha"],
    }
    assert len(recorded_commits) == 1
    recorded_commit = recorded_commits.pop()
    assert re.fullmatch(r"[0-9a-f]{40}", recorded_commit)
    recorded_object_available = subprocess.run(
        ["git", "cat-file", "-e", f"{recorded_commit}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    ).returncode == 0
    shallow_repository = subprocess.check_output(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=ROOT,
        text=True,
    ).strip() == "true"
    if recorded_object_available:
        ancestry_verified = _is_ancestor(recorded_commit, head)
        assert ancestry_verified, {
            "recorded_commit": recorded_commit,
            "checkout_head": head,
            "shallow_repository": shallow_repository,
        }
    else:
        assert shallow_repository

    parity = summary["cross_environment_parity"]
    host_code = _json(ROOT / runner.HOST_CODE_REFERENCE_RELATIVE_PATH)
    host_modal = _json(ROOT / runner.HOST_MODAL_REFERENCE_RELATIVE_PATH)
    assert parity == runner._cross_environment_parity(
        repo_root=ROOT,
        code_receipt=code,
        modal_receipt=modal,
        host_code_reference=host_code,
        host_modal_reference=host_modal,
        require_contract_pass=False,
    )
    container_scalar_count = len(runner._metric_scalar_map(code)) + len(
        runner._metric_scalar_map(modal)
    )
    host_scalar_count = len(runner._metric_scalar_map(host_code)) + len(
        runner._metric_scalar_map(host_modal)
    )
    assert parity["container_scalar_count"] == container_scalar_count
    assert parity["host_scalar_count"] == host_scalar_count
    assert parity["scalar_comparison_count"] == min(
        container_scalar_count, host_scalar_count
    )
    container_settlement_attached = any(
        row["case_id"] == "bounded_planar_prescribed_settlement_load_path"
        for row in code["comparisons"]
    )
    host_settlement_attached = any(
        row["case_id"] == "bounded_planar_prescribed_settlement_load_path"
        for row in host_code["comparisons"]
    )
    container_frame3d_attached = any(
        row["case_id"] == "spatial_frame3d_cantilever_combined_load"
        for row in code["comparisons"]
    )
    host_frame3d_attached = any(
        row["case_id"] == "spatial_frame3d_cantilever_combined_load"
        for row in host_code["comparisons"]
    )
    container_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_axial_yield"
        for row in code["comparisons"]
    )
    host_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_axial_yield"
        for row in host_code["comparisons"]
    )
    container_cyclic_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_cyclic_axial_reversal"
        for row in code["comparisons"]
    )
    host_cyclic_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_cyclic_axial_reversal"
        for row in host_code["comparisons"]
    )
    container_torsion_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_torsion"
        for row in code["comparisons"]
    )
    host_torsion_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_torsion"
        for row in host_code["comparisons"]
    )
    container_bending_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_bending_rotations"
        for row in code["comparisons"]
    )
    host_bending_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_bending_rotations"
        for row in host_code["comparisons"]
    )
    assert container_settlement_attached is host_settlement_attached
    assert container_frame3d_attached is host_frame3d_attached
    assert container_direct_control_attached is host_direct_control_attached
    assert (
        container_cyclic_direct_control_attached
        is host_cyclic_direct_control_attached
    )
    assert (
        container_torsion_direct_control_attached
        is host_torsion_direct_control_attached
    )
    assert (
        container_bending_direct_control_attached
        is host_bending_direct_control_attached
    )
    assert container_scalar_count == host_scalar_count
    assert container_scalar_count == (
        89
        + (18 if container_settlement_attached else 0)
        + (20 if container_frame3d_attached else 0)
        + (16 if container_direct_control_attached else 0)
        + (38 if container_cyclic_direct_control_attached else 0)
        + (6 if container_torsion_direct_control_attached else 0)
        + (12 if container_bending_direct_control_attached else 0)
    )
    expected_source_set_match = bool(
        code["internal_source"]["source_set_hash"]
        == host_code["internal_source"]["source_set_hash"]
        and modal["internal_source"]["source_set_hash"]
        == host_modal["internal_source"]["source_set_hash"]
    )
    assert parity["source_set_match"] is expected_source_set_match
    assert parity["metric_set_match"] is True
    assert parity["container_only_metric_keys"] == []
    assert parity["host_only_metric_keys"] == []
    assert parity["semantic_hash_matches"]["modal_model_hash"] is True
    assert parity["semantic_hash_matches"]["buckling_model_hash"] is True
    assert parity["exact_semantic_hash_parity"] is all(
        parity["semantic_hash_matches"].values()
    )
    assert summary["claims"]["cross_environment_numerical_parity"] is parity[
        "numerical_contract_pass"
    ]
    assert (
        runner.CROSS_ENVIRONMENT_PARITY_BLOCKER
        in summary["blockers_remaining"]
    ) is (not parity["numerical_contract_pass"])


def test_cross_environment_metric_set_drift_is_explicit_and_nonpromoting() -> None:
    container_code = _json(CODE_RECEIPT)
    container_modal = _json(MODAL_RECEIPT)
    host_code = deepcopy(container_code)
    host_code["comparisons"] = [
        row
        for row in host_code["comparisons"]
        if row["case_id"]
        != "bounded_planar_prescribed_settlement_load_path"
    ]

    parity = runner._cross_environment_parity(
        repo_root=ROOT,
        code_receipt=container_code,
        modal_receipt=container_modal,
        host_code_reference=host_code,
        host_modal_reference=container_modal,
        require_contract_pass=False,
    )

    assert parity["source_set_match"] is True
    assert parity["metric_set_match"] is False
    assert parity["numerical_contract_pass"] is False
    assert parity["scalar_comparison_count"] == 181
    assert parity["container_scalar_count"] == 199
    assert parity["host_scalar_count"] == 181
    assert len(parity["container_only_metric_keys"]) == 18
    assert parity["host_only_metric_keys"] == []
    assert all(
        key.startswith(
            "code_to_code/bounded_planar_prescribed_settlement_load_path/"
        )
        for key in parity["container_only_metric_keys"]
    )

    with pytest.raises(
        runner.CleanRunnerError,
        match="cross_environment_metric_set_mismatch",
    ):
        runner._cross_environment_parity(
            repo_root=ROOT,
            code_receipt=container_code,
            modal_receipt=container_modal,
            host_code_reference=host_code,
            host_modal_reference=container_modal,
        )


def test_cross_environment_source_commit_drift_fails_closed() -> None:
    container_code = _json(CODE_RECEIPT)
    container_modal = _json(MODAL_RECEIPT)
    host_code = deepcopy(container_code)
    host_code["source_commit_sha"] = "0" * 40

    parity = runner._cross_environment_parity(
        repo_root=ROOT,
        code_receipt=container_code,
        modal_receipt=container_modal,
        host_code_reference=host_code,
        host_modal_reference=container_modal,
        require_contract_pass=False,
    )
    assert parity["source_set_match"] is False
    assert parity["numerical_contract_pass"] is False

    with pytest.raises(
        runner.CleanRunnerError,
        match="cross_environment_source_set_mismatch",
    ):
        runner._cross_environment_parity(
            repo_root=ROOT,
            code_receipt=container_code,
            modal_receipt=container_modal,
            host_code_reference=host_code,
            host_modal_reference=container_modal,
        )


def test_rehashed_level2_or_independent_operator_promotion_is_rejected() -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["claims"]["verification_level_2"] = True
    payload["claims"]["independent_operator_attestation"] = True
    payload["artifact_hash"] = runner._artifact_hash(payload)

    with pytest.raises(ValidationError):
        runner.validate_summary(payload, repo_root=ROOT)


def test_rehashed_replay_summary_cannot_misstate_current_container_run() -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["runner"].update(
        {
            "runner_source_sha256": runner._file_hash(RUNNER),
            "schema_sha256": runner._file_hash(ROOT / runner.SCHEMA_RELATIVE_PATH),
            "dockerfile_sha256": runner._file_hash(
                ROOT / runner.DOCKERFILE_RELATIVE_PATH
            ),
            "wrapper_sha256": runner._file_hash(
                ROOT / runner.WRAPPER_RELATIVE_PATH
            ),
        }
    )
    claim = "same_operator_container_isolated_reproduction"
    payload["claims"][claim] = not payload["claims"][claim]
    payload["artifact_hash"] = runner._artifact_hash(payload)

    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_claims_invalid",
    ):
        runner.validate_summary(payload, repo_root=ROOT)


def test_summary_validation_uses_an_isolated_materialized_evidence_root(
    tmp_path: Path,
) -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["runner"].update(
        {
            "runner_source_sha256": runner._file_hash(RUNNER),
            "schema_sha256": runner._file_hash(ROOT / runner.SCHEMA_RELATIVE_PATH),
            "dockerfile_sha256": runner._file_hash(
                ROOT / runner.DOCKERFILE_RELATIVE_PATH
            ),
            "wrapper_sha256": runner._file_hash(
                ROOT / runner.WRAPPER_RELATIVE_PATH
            ),
        }
    )
    payload["artifact_hash"] = runner._artifact_hash(payload)
    evidence_root = tmp_path / "materialized-evidence"
    _materialize_summary_evidence(evidence_root, payload)

    runner.validate_summary(
        payload,
        repo_root=ROOT,
        evidence_root=evidence_root,
    )

    child_relative = Path(payload["product_receipts"]["code_to_code"]["path"])
    materialized_child = evidence_root / child_relative
    materialized_child.write_text(
        materialized_child.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_child_receipt_descriptor_invalid",
    ):
        runner.validate_summary(
            payload,
            repo_root=ROOT,
            evidence_root=evidence_root,
        )


def test_materialized_evidence_does_not_fall_back_to_tracked_receipts(
    tmp_path: Path,
) -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["runner"].update(
        {
            "runner_source_sha256": runner._file_hash(RUNNER),
            "schema_sha256": runner._file_hash(ROOT / runner.SCHEMA_RELATIVE_PATH),
            "dockerfile_sha256": runner._file_hash(
                ROOT / runner.DOCKERFILE_RELATIVE_PATH
            ),
            "wrapper_sha256": runner._file_hash(
                ROOT / runner.WRAPPER_RELATIVE_PATH
            ),
        }
    )
    payload["artifact_hash"] = runner._artifact_hash(payload)
    evidence_root = tmp_path / "materialized-evidence"
    _materialize_summary_evidence(evidence_root, payload)
    missing_relative = Path(
        payload["product_receipts"]["modal_buckling"]["path"]
    )
    (evidence_root / missing_relative).unlink()

    assert (ROOT / missing_relative).is_file()
    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_child_receipt_missing",
    ):
        runner.validate_summary(
            payload,
            repo_root=ROOT,
            evidence_root=evidence_root,
        )


def test_materialized_evidence_paths_cannot_escape_the_staging_root(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "materialized-evidence"
    evidence_root.mkdir()

    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_evidence_path_escape",
    ):
        runner._evidence_path(
            evidence_root=evidence_root,
            relative_path=Path("../outside.json"),
            missing_code="unused",
        )
    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_evidence_path_must_be_relative",
    ):
        runner._evidence_path(
            evidence_root=evidence_root,
            relative_path=ROOT / runner.HOST_CODE_REFERENCE_RELATIVE_PATH,
            missing_code="unused",
        )
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    (evidence_root / "linked.json").symlink_to(outside)
    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_evidence_path_escape",
    ):
        runner._evidence_path(
            evidence_root=evidence_root,
            relative_path=Path("linked.json"),
            missing_code="unused",
        )


def test_runner_package_pins_the_base_and_keeps_output_scope_explicit() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")

    assert f"FROM {runner.BASE_IMAGE.removeprefix('docker.io/library/')}" in dockerfile
    assert "numpy==1.26.4" in dockerfile
    assert "scipy==1.12.0" in dockerfile
    assert "libopenmpi3" in dockerfile
    wrapper = (ROOT / "scripts/run_external_vv_clean_runner.sh").read_text(
        encoding="utf-8"
    )
    assert "--provenance=false" in wrapper
    assert "--refresh-product-replay" in wrapper
    assert "--host-code-reference" in wrapper
    assert "--host-modal-reference" in wrapper
    assert "--network none" in readme
    assert "--read-only" in readme
    assert "independent_operator_attestation" in readme

    with pytest.raises(
        runner.CleanRunnerError, match="output_directory_must_be_inside_repo"
    ):
        runner._relative_to_repo(Path("/tmp/out"), ROOT)
