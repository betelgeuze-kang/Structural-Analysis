from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/classify_native_ci_scope.py"
SPEC = importlib.util.spec_from_file_location("native_metadata_proposal", SCRIPT)
assert SPEC and SPEC.loader
scope = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scope
SPEC.loader.exec_module(scope)
PROTECTED = list(scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS)
PHYSICAL = scope._METADATA_PREFIX + "synthetic-reference-never-materialized.json"


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def write(repo, name, data):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def checksum(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def commit(repo, message):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def case(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "--quiet")
    git(repo, "config", "user.name", "Synthetic policy test")
    git(repo, "config", "user.email", "synthetic-policy-test@example.invalid")
    software = sorted(set().union(*scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS.values()))
    for path in software:
        write(repo, path, b"original source\n")
    write(repo, PHYSICAL, b"unread synthetic artifact\n")
    anchor = commit(repo, "immutable synthetic inputs")
    payloads = {}
    for path, keys in scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS.items():
        payloads[path] = {
            "generated_at": "2026-10-21T00:00:00+00:00",
            "source_commit_sha": anchor,
            "input_checksums": {
                key: checksum(b"original source\n") for key in sorted(keys)
            },
            "claim_boundary": {
                "hardware_authority": False,
                "physical_qualified": False,
            },
            "outcome": "max_iterations",
            "limits": {"iterations": 30, "tolerance": 1e-9, "budget": 120},
            "values": [1.0, 0.0, -2.0],
        }
        # Deliberately unverified content checksum: equal Git reference custody
        # must not be represented as fresh content or physical validation.
        payloads[path]["input_checksums"][PHYSICAL] = "sha256:" + "0" * 64
        write(repo, path, json.dumps(payloads[path], sort_keys=True))
    base = commit(repo, "immutable synthetic receipt baseline")
    return {"repo": repo, "base": base, "payloads": payloads, "software": software}


def stage(case, mutator=None, all_paths=True):
    paths = PROTECTED if all_paths else PROTECTED[:1]
    for path in paths:
        payload = deepcopy(case["payloads"][path])
        payload["generated_at"] = "2026-10-22T00:00:00Z"
        payload["source_commit_sha"] = case["base"]
        if mutator:
            mutator(payload, path)
        write(case["repo"], path, json.dumps(payload, sort_keys=True))
    return commit(case["repo"], "synthetic proposed metadata projection")


def validate(case, head, paths=PROTECTED):
    return scope.validate_protected_metadata_changes(
        base=case["base"], head=head, repo_root=case["repo"], protected_paths=paths
    )


def test_all_five_metadata_projections_pass_and_remain_protected(case, monkeypatch):
    physical_oid = scope._metadata_reference(case["repo"], case["base"], PHYSICAL)[1]
    original_blob = scope._metadata_blob

    def refuse_artifact_reads(repo, oid, limit):
        assert oid != physical_oid, "unchanged physical reference contents were read"
        return original_blob(repo, oid, limit)

    monkeypatch.setattr(scope, "_metadata_blob", refuse_artifact_reads)
    head = stage(case)
    result = validate(case, head)
    assert result["contract_pass"] is True
    assert len(result["validated_receipts"]) == 5
    assert "does not revalidate their contents" in result["authority_boundary"]
    assert scope.classify_paths(PROTECTED)["protected_evidence"] is True
    for receipt in result["validated_receipts"]:
        assert all(
            row["binding"] == "unchanged_reference_git_blob_identity_only"
            for row in receipt["input_references"]
        )


def test_changed_finite_software_checksum_is_bound_to_exact_head_bytes(case):
    for source_path in case["software"]:
        write(case["repo"], source_path, b"changed software source\n")

    def mutate(payload, path):
        for source_path in scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]:
            payload["input_checksums"][source_path] = checksum(
                b"changed software source\n"
            )

    result = validate(case, stage(case, mutate))
    assert result["contract_pass"] is True
    rows = [r for x in result["validated_receipts"] for r in x["input_references"]]
    assert any(r["binding"] == "changed_software_exact_head_bytes" for r in rows)
    assert (
        next(r for r in rows if r["path"] == PHYSICAL)["binding"]
        == "unchanged_reference_git_blob_identity_only"
    )


def test_cli_keeps_flag_and_protected_output_with_explicit_validation(
    case, tmp_path, capsys
):
    head = stage(case)
    output = tmp_path / "outputs.txt"
    code = scope.main(
        [
            "--base",
            case["base"],
            "--head",
            head,
            "--repo-root",
            str(case["repo"]),
            "--fail-protected-evidence",
            "--github-output",
            str(output),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["protected_evidence"] is True
    assert result["metadata_only_validation"]["contract_pass"] is True
    assert "protected_evidence=true\n" in output.read_text()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda x, _: x["claim_boundary"].update(hardware_authority=True),
        lambda x, _: x["claim_boundary"].update(physical_qualified=True),
        lambda x, _: x["limits"].update(iterations=31),
        lambda x, _: x["limits"].update(tolerance=1e-8),
        lambda x, _: x["limits"].update(budget=121),
        lambda x, _: x.update(outcome="success"),
        lambda x, _: x.update(extra="unapproved"),
        lambda x, _: x.pop("outcome"),
        lambda x, _: x["values"].reverse(),
        lambda x, _: x["values"].append(3.0),
        lambda x, _: x["values"].__setitem__(1, -0.0),
        lambda x, _: x["limits"].update(iterations=30.0),
        lambda x, _: x["claim_boundary"].update(hardware_authority=0),
        lambda x, _: x["input_checksums"].update({PHYSICAL: "sha256:" + "f" * 64}),
        lambda x, _: x["input_checksums"].update(
            {"new-input.py": "sha256:" + "f" * 64}
        ),
        lambda x, _: x["input_checksums"].pop(PHYSICAL),
        lambda x, _: x.update(generated_at="2026-10-22T00:00:00"),
        lambda x, _: x.update(generated_at="2026-10-22T01:00:00+01:00"),
        lambda x, _: x.update(generated_at="not-a-date"),
        lambda x, _: x.update(source_commit_sha="main"),
        lambda x, _: x.update(source_commit_sha="f" * 40),
    ],
)
def test_numerical_claim_key_shape_checksum_and_provenance_mutations_block(
    case, mutator
):
    result = validate(case, stage(case, mutator))
    assert result["contract_pass"] is False
    assert result["blockers"]


def test_wrong_allowed_software_checksum_blocks(case):
    def mutate(payload, path):
        key = next(iter(scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]))
        payload["input_checksums"][key] = "sha256:" + "f" * 64

    result = validate(case, stage(case, mutate))
    assert result["blockers"] == ["changed_software_checksum_head_bytes_mismatch"]


def test_unchanged_checksum_reference_with_changed_software_blob_blocks(case):
    write(
        case["repo"], case["software"][0], b"source changed without checksum refresh\n"
    )
    result = validate(case, stage(case))
    assert result["blockers"] == ["unchanged_checksum_reference_blob_changed"]


def test_unchanged_physical_reference_blob_change_blocks_without_reading_it(
    case, monkeypatch
):
    old_oid = scope._metadata_reference(case["repo"], case["base"], PHYSICAL)[1]
    write(case["repo"], PHYSICAL, b"different physical artifact\n")
    head = stage(case)
    new_oid = scope._metadata_reference(case["repo"], head, PHYSICAL)[1]
    original_blob = scope._metadata_blob

    def guarded(repo, oid, limit):
        assert oid not in {old_oid, new_oid}
        return original_blob(repo, oid, limit)

    monkeypatch.setattr(scope, "_metadata_blob", guarded)
    result = validate(case, head, [*PROTECTED, PHYSICAL])
    assert result["blockers"] == ["unknown_protected_path"]


def test_unchanged_nonprotected_reference_blob_change_also_blocks(case):
    source = case["software"][0]
    write(case["repo"], source, b"unrefreshed source\n")
    result = validate(case, stage(case))
    assert result["blockers"] == ["unchanged_checksum_reference_blob_changed"]


@pytest.mark.parametrize(
    "unknown",
    [
        scope._METADATA_PREFIX + "new-receipt.json",
        ".betelgeuze/intent_spec.md",
        "docs/commercial-structural-solver-product-gap-ledger.md",
        "docs/structural-analysis-ai-engine-gap-ledger.md",
    ],
)
def test_every_other_protected_path_remains_blocked(case, unknown):
    write(case["repo"], unknown, b"synthetic prohibited change\n")
    result = validate(case, stage(case), [*PROTECTED, unknown])
    assert result["blockers"] == ["unknown_protected_path"]


def test_omitted_protected_path_inventory_cannot_authorize_subset(case):
    result = validate(case, stage(case), PROTECTED[:1])
    assert result["blockers"] == ["protected_diff_inventory_mismatch"]


def test_added_approved_receipt_is_not_metadata_refresh(case):
    git(case["repo"], "rm", "--quiet", PROTECTED[0])
    case["base"] = commit(case["repo"], "baseline without one receipt")
    result = validate(case, stage(case))
    assert result["blockers"] == ["input_reference_missing_or_nonregular"]


def test_deleted_approved_receipt_is_rejected(case):
    head = stage(case)
    git(case["repo"], "rm", "--quiet", PROTECTED[0])
    head = commit(case["repo"], "delete protected receipt")
    result = validate(case, head)
    assert result["blockers"] == ["input_reference_missing_or_nonregular"]


def test_receipt_symlink_is_rejected(case):
    stage(case)
    path = case["repo"] / PROTECTED[0]
    path.unlink()
    path.symlink_to("../../../../README.md")
    result = validate(case, commit(case["repo"], "symlink receipt"))
    assert result["blockers"] == ["input_reference_missing_or_nonregular"]


def test_protected_rename_reports_both_names_and_blocks(case):
    stage(case)
    unknown = scope._METADATA_PREFIX + "renamed.json"
    git(case["repo"], "mv", PROTECTED[0], unknown)
    result = validate(
        case, commit(case["repo"], "rename protected receipt"), [*PROTECTED, unknown]
    )
    assert result["blockers"] == ["unknown_protected_path"]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"generated_at": "x", "generated_at": "y"}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":1e999}',
        b"[]",
        b"not json",
        b"\xff",
    ],
)
def test_malformed_duplicate_nonfinite_or_nonobject_receipts_block(case, raw):
    stage(case)
    write(case["repo"], PROTECTED[0], raw)
    result = validate(case, commit(case["repo"], "malformed receipt"))
    assert result["contract_pass"] is False


def test_unknown_source_commit_not_ancestor_blocks(case):
    git(case["repo"], "checkout", "--quiet", "--orphan", "unrelated")
    write(case["repo"], "unrelated.txt", b"unrelated tree\n")
    unrelated = commit(case["repo"], "unrelated commit")
    git(case["repo"], "checkout", "--quiet", "--detach", case["base"])
    result = validate(
        case, stage(case, lambda x, _: x.update(source_commit_sha=unrelated))
    )
    assert result["blockers"] == ["receipt_source_ancestry_not_proven"]


def test_changed_software_lfs_pointer_is_not_data_checksum_proof(case):
    key = case["software"][0]
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\noid sha256:"
        + b"f" * 64
        + b"\nsize 10\n"
    )
    write(case["repo"], key, pointer)

    def mutate(payload, path):
        if key in scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]:
            payload["input_checksums"][key] = checksum(pointer)

    result = validate(case, stage(case, mutate))
    assert result["blockers"] == ["changed_software_input_is_lfs_pointer"]


def test_manual_path_override_cannot_authorize_protected_change(capsys):
    result = scope.main(["--path", PROTECTED[0], "--fail-protected-evidence"])
    output = json.loads(capsys.readouterr().out)
    assert result == 3
    assert output["protected_evidence"] is True
    assert output["metadata_only_validation"]["contract_pass"] is False


def test_wrong_immutable_head_and_base_cannot_validate(case):
    head = stage(case)
    for base, candidate in (("main", head), (case["base"], "HEAD"), ("f" * 40, head)):
        result = scope.validate_protected_metadata_changes(
            base=base, head=candidate, repo_root=case["repo"], protected_paths=PROTECTED
        )
        assert result["contract_pass"] is False


def test_absent_producer_history_in_shallow_checkout_fails_closed(case, tmp_path):
    head = stage(
        case,
        lambda x, _: x.update(
            source_commit_sha=case["payloads"][PROTECTED[0]]["source_commit_sha"]
        ),
    )
    clone = tmp_path / "shallow"
    subprocess.check_call(
        [
            "git",
            "clone",
            "--quiet",
            "--depth=2",
            "--no-local",
            "--branch",
            git(case["repo"], "branch", "--show-current"),
            str(case["repo"]),
            str(clone),
        ]
    )
    result = scope.validate_protected_metadata_changes(
        base=case["base"], head=head, repo_root=clone, protected_paths=PROTECTED
    )
    assert result["contract_pass"] is False
    assert result["blockers"] == ["immutable_git_object_unavailable"]


def test_unprotected_native_diff_retains_original_behavior(capsys):
    code = scope.main(["--path", "native/Cargo.toml", "--fail-protected-evidence"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["native"] is True
    assert result["protected_evidence"] is False
    assert "metadata_only_validation" not in result


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "secret.env",
        "secret.env.production",
        "../outside",
        "/absolute",
    ],
)
def test_secret_or_escaping_reference_never_reads_a_blob(case, name, monkeypatch):
    def no_git(*_args):
        raise AssertionError("Git must not be called for an invalid reference")

    monkeypatch.setattr(scope, "_metadata_git", no_git)
    with pytest.raises(ValueError):
        scope._metadata_reference(case["repo"], case["base"], name)


def test_depth32_checkout_proves_existing_producer_ancestry(case, tmp_path):
    head = stage(
        case,
        lambda x, _: x.update(
            source_commit_sha=case["payloads"][PROTECTED[0]]["source_commit_sha"]
        ),
    )
    clone = tmp_path / "bounded32"
    subprocess.check_call(
        [
            "git",
            "clone",
            "--quiet",
            "--depth=32",
            "--no-local",
            "--branch",
            git(case["repo"], "branch", "--show-current"),
            str(case["repo"]),
            str(clone),
        ]
    )
    result = scope.validate_protected_metadata_changes(
        base=case["base"], head=head, repo_root=clone, protected_paths=PROTECTED
    )
    assert result["contract_pass"] is True


def test_receipt_parser_recursion_is_indeterminate_and_blocked(case):
    stage(case)
    write(case["repo"], PROTECTED[0], b"[" * 2000 + b"0" + b"]" * 2000)
    result = validate(case, commit(case["repo"], "excessive JSON nesting"))
    assert result["contract_pass"] is False


def test_changed_software_validation_budget_is_fail_closed(case, monkeypatch):
    for source_path in case["software"]:
        write(
            case["repo"],
            source_path,
            b"changed source larger than finite validator limit\n",
        )

    def mutate(payload, path):
        for key in scope.METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]:
            payload["input_checksums"][key] = checksum(
                b"changed source larger than finite validator limit\n"
            )

    monkeypatch.setattr(scope, "_MAX_SOFTWARE_INPUT_BYTES", 8)
    result = validate(case, stage(case, mutate))
    assert result["blockers"] == ["immutable_blob_exceeds_validation_budget"]


@pytest.mark.parametrize(
    "filename",
    [
        PROTECTED[0] + " ",
        " " + PROTECTED[0],
        PROTECTED[0] + "\n",
        PROTECTED[0].replace("/", "\\"),
    ],
)
def test_raw_git_path_cannot_normalize_into_allowed_protected_name(case, filename):
    stage(case)
    write(case["repo"], filename, b"unknown protected content\n")
    result = validate(case, commit(case["repo"], "noncanonical protected filename"))
    assert result["blockers"] == ["noncanonical_changed_git_path"]


def test_executable_receipt_mode_is_not_a_metadata_refresh(case):
    stage(case)
    path = case["repo"] / PROTECTED[0]
    path.chmod(0o755)
    result = validate(case, commit(case["repo"], "unexpected receipt executable mode"))
    assert result["blockers"] == ["receipt_mode_must_be_regular_100644"]


@pytest.mark.parametrize("kind", ["symlink", "gitlink"])
@pytest.mark.parametrize("diff_route", ["ordinary", "root_diff_tree"])
def test_actual_cli_protects_receipt_type_change_without_other_receipt_edits(
    case, kind, diff_route
):
    repo = case["repo"]
    path = repo / PROTECTED[0]
    path.unlink()
    write(repo, "native/Cargo.toml", b"[workspace]\n")
    if kind == "symlink":
        path.symlink_to("../../../../README.md")
        head = commit(repo, "protected receipt symlink plus native source")
    else:
        git(repo, "add", "native/Cargo.toml")
        git(
            repo,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{case['base']},{PROTECTED[0]}",
        )
        git(
            repo,
            "commit",
            "--quiet",
            "-m",
            "protected receipt gitlink plus native source",
        )
        head = git(repo, "rev-parse", "HEAD")
    base = case["base"] if diff_route == "ordinary" else "0" * 40
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--head",
            head,
            "--fail-protected-evidence",
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 3
    assert payload["native"] is True
    assert payload["protected_evidence"] is True
    assert payload["protected_evidence_paths"] == [PROTECTED[0]]
    assert payload["metadata_only_validation"]["contract_pass"] is False
    if diff_route == "ordinary":
        assert payload["metadata_only_validation"]["blockers"] == [
            "input_reference_missing_or_nonregular"
        ]


@pytest.mark.parametrize("diff_route", ["ordinary", "root_diff_tree"])
def test_actual_cli_protected_receipt_rename_to_unprotected_path_cannot_hide_source(
    case, diff_route
):
    repo = case["repo"]
    git(repo, "mv", PROTECTED[0], "unprotected-destination.json")
    write(repo, "native/Cargo.toml", b"[workspace]\n")
    head = commit(repo, "rename protected receipt outside protected prefix")
    base = case["base"] if diff_route == "ordinary" else "0" * 40
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--head",
            head,
            "--fail-protected-evidence",
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 3
    assert payload["protected_evidence"] is True
    assert PROTECTED[0] in payload["protected_evidence_paths"]
    assert "unprotected-destination.json" in payload["changed_paths"]
    assert payload["metadata_only_validation"]["contract_pass"] is False


def test_actual_cli_zero_base_merge_head_cannot_suppress_protected_type_change(case):
    repo = case["repo"]
    initial_branch = git(repo, "branch", "--show-current")
    git(repo, "checkout", "--quiet", "-b", "feature-with-type-change")
    path = repo / PROTECTED[0]
    path.unlink()
    path.symlink_to("../../../../README.md")
    write(repo, "native/Cargo.toml", b"[workspace]\n")
    commit(repo, "protected receipt type change")
    git(repo, "checkout", "--quiet", initial_branch)
    write(repo, "independent-parent-marker.txt", b"independent parent\n")
    commit(repo, "independent parent")
    git(
        repo,
        "merge",
        "--quiet",
        "--no-ff",
        "feature-with-type-change",
        "-m",
        "merge protected type change",
    )
    head = git(repo, "rev-parse", "HEAD")
    assert len(git(repo, "show", "-s", "--format=%P", head).split()) == 2
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--base",
            "0" * 40,
            "--head",
            head,
            "--fail-protected-evidence",
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 3
    assert payload["native"] is True
    assert payload["protected_evidence"] is True
    assert PROTECTED[0] in payload["protected_evidence_paths"]
    assert payload["metadata_only_validation"]["contract_pass"] is False
