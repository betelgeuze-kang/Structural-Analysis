from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

from scripts import check_generated_artifact_dag as module


ROOT = Path(__file__).resolve().parents[1]


def test_git_commands_scope_safe_directory_to_resolved_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        observed["cwd"] = kwargs["cwd"]
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    completed = module._git_run(tmp_path, "rev-parse", "HEAD")

    assert completed.stdout == "ok\n"
    assert observed["command"] == [
        "/usr/bin/git",
        "-c",
        f"safe.directory={tmp_path.resolve()}",
        "rev-parse",
        "HEAD",
    ]
    assert observed["cwd"] == tmp_path
    assert observed["env"] == {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def test_direct_script_bootstraps_repo_root_without_pythonpath() -> None:
    script = ROOT / "scripts/check_generated_artifact_dag.py"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    code = (
        "import runpy, sys; "
        f"runpy.run_path({str(script)!r}, run_name='dag_path_probe'); "
        f"assert {str(ROOT)!r} in sys.path; "
        "import scripts.generate_capability_surfaces"
    )
    completed = subprocess.run(
        [sys.executable, "-S", "-c", code],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _semantic_release_leaf_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    from scripts import build_pm_release_blocker_action_register as action
    from scripts import build_pm_release_blocker_closure_board as closure
    from scripts import build_product_readiness_snapshot as readiness
    from scripts import build_structural_product_development_roadmap as roadmap
    from scripts import report_pm_release_gate as pm

    for imported in (action, closure, readiness, roadmap, pm):
        if hasattr(imported, "ROOT"):
            monkeypatch.setattr(imported, "ROOT", tmp_path)
    for relative in module.POST_MAIN_RELEASE_EVIDENCE_INPUTS[1:]:
        _write(tmp_path / relative, f"source:{relative}\n")

    payloads: dict[str, dict[str, Any]] = {}
    for relative in module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1:]:
        payloads[relative] = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_bytes(
            module._canonical_json_bytes(payloads[relative])
        )

    def clone(relative: str) -> dict[str, Any]:
        return json.loads(json.dumps(payloads[relative]))

    observed: dict[str, Any] = {"order": []}

    def build_pm(**kwargs: Any) -> dict[str, Any]:
        observed["order"].append("pm")
        observed["pm_kwargs"] = kwargs
        return clone(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1])

    def build_action(**kwargs: Any) -> dict[str, Any]:
        observed["order"].append("action")
        observed["action_kwargs"] = kwargs
        observed["action_pm"] = json.loads(
            (action.ROOT / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]).read_text(
                encoding="utf-8"
            )
        )
        return clone(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2])

    def build_closure(**_: Any) -> dict[str, Any]:
        observed["order"].append("closure")
        observed["closure_action"] = json.loads(
            (closure.ROOT / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]).read_text(
                encoding="utf-8"
            )
        )
        return clone(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[3])

    def build_readiness(*, repo_root: Path, **_: Any) -> dict[str, Any]:
        observed["order"].append("readiness")
        observed["readiness_action"] = json.loads(
            (repo_root / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]).read_text(
                encoding="utf-8"
            )
        )
        return clone(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[4])

    def build_roadmap(*, repo_root: Path, **_: Any) -> dict[str, Any]:
        observed["order"].append("roadmap")
        observed["roadmap_readiness"] = json.loads(
            (repo_root / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[4]).read_text(
                encoding="utf-8"
            )
        )
        return clone(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[5])

    monkeypatch.setattr(
        pm,
        "build_report",
        build_pm,
    )
    monkeypatch.setattr(
        action,
        "build_register",
        build_action,
    )
    monkeypatch.setattr(
        closure,
        "build_board",
        build_closure,
    )
    monkeypatch.setattr(
        readiness,
        "build_snapshot",
        build_readiness,
    )
    monkeypatch.setattr(
        roadmap,
        "build_structural_product_development_roadmap",
        build_roadmap,
    )
    roadmap_md = tmp_path / (
        "implementation/phase1/release_evidence/productization/"
        "structural_product_development_roadmap.md"
    )
    _write(
        roadmap_md,
        roadmap._markdown(payloads[module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[5]]),
    )

    @contextmanager
    def isolated_fixture_root(repo_root: Path):
        with tempfile.TemporaryDirectory(
            prefix="dag-semantic-replay-test-", dir=repo_root.parent
        ) as temporary:
            replay_root = Path(temporary) / "repo"
            shutil.copytree(repo_root, replay_root)
            yield replay_root

    monkeypatch.setattr(
        module,
        "_isolated_release_leaf_replay_root",
        isolated_fixture_root,
    )

    def fake_git(repo_root: Path, *args: str, text: bool = True):
        relative = args[-1].split(":", 1)[1]
        raw = (repo_root / relative).read_bytes()
        return SimpleNamespace(returncode=0, stdout=raw if not text else raw.decode())

    monkeypatch.setattr(module, "_git_run", fake_git)
    return {
        "pm": tmp_path / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1],
        "action": tmp_path / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2],
        "roadmap": tmp_path / module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[5],
        "roadmap_md": roadmap_md,
        "payloads": payloads,
        "observed": observed,
        "roadmap_module": roadmap,
    }


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(module._canonical_json_bytes(payload))


def _assert_semantic_mismatch(violations: list[str], relative: str) -> None:
    assert f"release_leaf_semantic_replay_mismatch:{relative}" in violations


def test_post_main_release_leaf_semantic_replay_is_isolated_and_topological(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    payload = json.loads(paths["pm"].read_text(encoding="utf-8"))
    payload["release_decision"]["release_allowed"] = True
    _write_payload(paths["pm"], payload)

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    _assert_semantic_mismatch(violations, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1])
    assert paths["observed"]["order"] == [
        "pm",
        "action",
        "closure",
        "readiness",
        "roadmap",
    ]
    from scripts import build_pm_release_blocker_action_register as action
    from scripts import report_pm_release_gate as pm

    assert paths["observed"]["pm_kwargs"] == {
        "github_sync_preflight": pm.DEFAULT_GITHUB_DEVELOPMENT_SYNC_PREFLIGHT,
    }
    assert paths["observed"]["action_kwargs"] == {
        "pm_report": Path(module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]),
        "structural_scope_plan": (
            action.DEFAULT_STRUCTURAL_SCOPE_OWNER_DECISION_APPLICATION_PLAN
        ),
    }
    assert (
        paths["observed"]["action_pm"]
        == paths["payloads"][module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]]
    )
    assert json.loads(paths["pm"].read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda payload: payload["release_decision"].__setitem__(
                "release_allowed", True
            ),
            id="release-allowed",
        ),
        pytest.param(
            lambda payload: payload.__setitem__("release_claims_fail_closed", False),
            id="fail-closed",
        ),
        pytest.param(
            lambda payload: payload["source_input_provenance"].__setitem__(
                "contract_pass", True
            ),
            id="provenance",
        ),
        pytest.param(
            lambda payload: payload["blockers"].append("forged:blocker"),
            id="blocker",
        ),
    ],
)
def test_post_main_release_leaf_semantic_replay_rejects_real_pm_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Any,
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    payload = json.loads(paths["pm"].read_text(encoding="utf-8"))
    mutate(payload)
    _write_payload(paths["pm"], payload)

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    _assert_semantic_mismatch(violations, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1])


def test_post_main_release_leaf_semantic_replay_rejects_real_action_row_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    payload = json.loads(paths["action"].read_text(encoding="utf-8"))
    payload["rows"][0]["status"] = "closed"
    _write_payload(paths["action"], payload)

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    _assert_semantic_mismatch(violations, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2])


def test_post_main_release_leaf_semantic_replay_rejects_roadmap_markdown_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    paths["roadmap_md"].write_text("tampered\n", encoding="utf-8")

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    assert any(
        violation.startswith("release_leaf_markdown_replay_mismatch:")
        for violation in violations
    )


def test_post_main_release_leaf_markdown_is_rendered_from_rebuilt_roadmap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    payload = json.loads(paths["roadmap"].read_text(encoding="utf-8"))
    payload["summary_line"] = "forged roadmap summary"
    _write_payload(paths["roadmap"], payload)
    paths["roadmap_md"].write_text(
        paths["roadmap_module"]._markdown(payload), encoding="utf-8"
    )

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    _assert_semantic_mismatch(violations, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[5])
    assert any(
        violation.startswith("release_leaf_markdown_replay_mismatch:")
        for violation in violations
    )


def test_release_leaf_compare_ignores_only_declared_root_volatility() -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    stored["generated_at"] = "2099-01-01T00:00:00+00:00"

    assert module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )

    stored["source_input_provenance"]["generated_at"] = "2099-01-01T00:00:00+00:00"
    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


def test_readiness_snapshot_compare_normalizes_only_environment_diagnostics() -> None:
    relative = module.PRODUCT_READINESS_SNAPSHOT
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    original_rebuilt = json.loads(json.dumps(rebuilt))
    stored_worktree = stored["state_consistency"]["worktree"]
    stored_worktree["status_rows"] = [" M producer-only.json"]
    stored_worktree["dirty_paths"] = ["producer-only.json"]

    assert module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )
    assert rebuilt == original_rebuilt

    stored_worktree["dirty"] = not rebuilt["state_consistency"]["worktree"]["dirty"]
    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda payload: payload["state_consistency"]["worktree"].__setitem__(
                "non_receipt_dirty_paths", ["tampered.json"]
            ),
            id="non-receipt-dirty-paths",
        ),
        pytest.param(
            lambda payload: payload["state_consistency"]["worktree"][
                "phase3_release_control_cleanup_plan"
            ].__setitem__("status", "tampered"),
            id="nested-worktree-state",
        ),
        pytest.param(
            lambda payload: payload.__setitem__("source_commit_sha", "f" * 40),
            id="source-commit",
        ),
        pytest.param(
            lambda payload: payload["state_consistency"]["metadata_rows"][
                0
            ].__setitem__("changed_paths_since_source_commit", ["tampered.json"]),
            id="metadata-row",
        ),
    ],
)
def test_readiness_snapshot_compare_rejects_adjacent_semantic_tamper(
    mutate: Any,
) -> None:
    relative = module.PRODUCT_READINESS_SNAPSHOT
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    mutate(stored)

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        pytest.param("status_rows", None, id="status-rows-missing"),
        pytest.param("dirty_paths", None, id="dirty-paths-missing"),
        pytest.param("status_rows", "not-a-list", id="status-rows-wrong-type"),
        pytest.param("dirty_paths", [1], id="dirty-path-item-wrong-type"),
    ],
)
def test_readiness_snapshot_compare_requires_diagnostic_shape(
    field: str, replacement: Any
) -> None:
    relative = module.PRODUCT_READINESS_SNAPSHOT
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    if replacement is None:
        stored["state_consistency"]["worktree"].pop(field)
    else:
        stored["state_consistency"]["worktree"][field] = replacement

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


def test_worktree_diagnostic_names_remain_semantic_outside_snapshot() -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    rebuilt["state_consistency"] = {
        "worktree": {"status_rows": [], "dirty_paths": []}
    }
    stored["state_consistency"] = {
        "worktree": {
            "status_rows": [" M producer-only.json"],
            "dirty_paths": ["producer-only.json"],
        }
    }

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


def test_materialize_preserves_snapshot_diagnostics_for_downstream_replay(
    tmp_path: Path,
) -> None:
    relative = module.PRODUCT_READINESS_SNAPSHOT
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    original_rebuilt = json.loads(json.dumps(rebuilt))
    stored_worktree = stored["state_consistency"]["worktree"]
    stored_worktree["status_rows"] = [" M producer-only.json"]
    stored_worktree["dirty_paths"] = ["producer-only.json"]

    module._materialize_rebuilt_release_leaf(
        replay_root=tmp_path,
        relative=relative,
        stored=stored,
        rebuilt=rebuilt,
    )

    materialized = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    assert materialized["state_consistency"]["worktree"]["status_rows"] == [
        " M producer-only.json"
    ]
    assert materialized["state_consistency"]["worktree"]["dirty_paths"] == [
        "producer-only.json"
    ]
    assert module._canonical_json_bytes(materialized) == module._canonical_json_bytes(
        stored
    )
    assert rebuilt == original_rebuilt


def test_materialize_does_not_preserve_snapshot_diagnostics_after_semantic_tamper(
    tmp_path: Path,
) -> None:
    relative = module.PRODUCT_READINESS_SNAPSHOT
    rebuilt = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    stored = json.loads(json.dumps(rebuilt))
    stored["state_consistency"]["worktree"]["status_rows"] = [
        " M producer-only.json"
    ]
    stored["state_consistency"]["worktree"]["dirty_paths"] = [
        "producer-only.json"
    ]
    stored["state_consistency"]["worktree"]["dirty"] = not rebuilt[
        "state_consistency"
    ]["worktree"]["dirty"]

    module._materialize_rebuilt_release_leaf(
        replay_root=tmp_path,
        relative=relative,
        stored=stored,
        rebuilt=rebuilt,
    )

    materialized = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    assert materialized["state_consistency"]["worktree"]["status_rows"] == rebuilt[
        "state_consistency"
    ]["worktree"]["status_rows"]
    assert materialized["state_consistency"]["worktree"]["dirty_paths"] == rebuilt[
        "state_consistency"
    ]["worktree"]["dirty_paths"]


def test_semantic_replay_accepts_cross_environment_snapshot_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _semantic_release_leaf_fixture(tmp_path, monkeypatch)
    relative = module.PRODUCT_READINESS_SNAPSHOT
    stored = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    stored["state_consistency"]["worktree"]["status_rows"] = [
        " M producer-only.json"
    ]
    stored["state_consistency"]["worktree"]["dirty_paths"] = [
        "producer-only.json"
    ]
    _write_payload(tmp_path / relative, stored)

    violations = module._validate_post_main_release_leaf_semantics(
        repo_root=tmp_path,
        expected_source_sha="a" * 40,
    )

    assert not any(relative in violation for violation in violations)
    replayed = paths["observed"]["roadmap_readiness"]
    assert replayed["state_consistency"]["worktree"]["status_rows"] == [
        " M producer-only.json"
    ]
    assert replayed["state_consistency"]["worktree"]["dirty_paths"] == [
        "producer-only.json"
    ]


def _guarded_cyclic_pm_payload(
    *, action_checksum_character: str, closure_checksum_character: str
) -> dict[str, Any]:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    provenance = payload["source_input_provenance"]
    cycle_blocker = (
        "cyclic_input_dependency:pm_release_gate_report->"
        "pm_release_blocker_action_register/pm_release_blocker_closure_board->"
        "pm_release_gate_report"
    )
    blockers = list(provenance["blockers"])
    if cycle_blocker not in blockers:
        blockers.append(cycle_blocker)
    checksum_characters = {
        module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]: action_checksum_character,
        module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[3]: closure_checksum_character,
    }
    for row in provenance["inputs"]:
        path = row.get("path")
        if path not in checksum_characters:
            continue
        blocker = f"input_differs_from_source_commit:{path}"
        if blocker not in blockers:
            blockers.append(blocker)
        row["workspace_checksum"] = "sha256:" + checksum_characters[path] * 64
        row["workspace_matches_source"] = False
        row["blocker"] = blocker
    provenance["blockers"] = blockers
    provenance["blocker_count"] = len(blockers)
    provenance["workspace_match_count"] = sum(
        row.get("workspace_matches_source") is True for row in provenance["inputs"]
    )
    provenance["contract_pass"] = False
    payload["release_claims_fail_closed"] = True
    payload["provenance_guard"].update(
        {
            "mode": "diagnostics_only_fail_closed",
            "dependency_dag_repaired": False,
            "direct_cycle_detected": True,
            "canonical_action_register_edge_detected": True,
            "canonical_closure_board_edge_detected": True,
        }
    )
    return payload


def _cyclic_input_row(payload: dict[str, Any], relative: str) -> dict[str, Any]:
    return next(
        row
        for row in payload["source_input_provenance"]["inputs"]
        if row.get("path") == relative
    )


def test_release_leaf_compare_normalizes_only_guarded_cycle_diagnostic_checksums() -> (
    None
):
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    original_stored = json.loads(json.dumps(stored))
    original_rebuilt = json.loads(json.dumps(rebuilt))

    assert module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )
    assert stored == original_stored
    assert rebuilt == original_rebuilt


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda payload: payload["provenance_guard"].__setitem__(
                "mode", "authoritative"
            ),
            id="guard-mode",
        ),
        pytest.param(
            lambda payload: payload["provenance_guard"].__setitem__(
                "dependency_dag_repaired", True
            ),
            id="dag-repaired",
        ),
        pytest.param(
            lambda payload: payload["provenance_guard"].__setitem__(
                "direct_cycle_detected", False
            ),
            id="cycle-not-detected",
        ),
        pytest.param(
            lambda payload: payload["provenance_guard"].__setitem__(
                "canonical_action_register_edge_detected", False
            ),
            id="action-edge-not-detected",
        ),
        pytest.param(
            lambda payload: payload["provenance_guard"].__setitem__(
                "canonical_closure_board_edge_detected", False
            ),
            id="closure-edge-not-detected",
        ),
        pytest.param(
            lambda payload: payload.__setitem__("release_claims_fail_closed", False),
            id="release-not-fail-closed",
        ),
        pytest.param(
            lambda payload: payload["source_input_provenance"].__setitem__(
                "contract_pass", True
            ),
            id="provenance-passes",
        ),
        pytest.param(
            lambda payload: payload["source_input_provenance"]["blockers"].remove(
                "cyclic_input_dependency:pm_release_gate_report->"
                "pm_release_blocker_action_register/pm_release_blocker_closure_board->"
                "pm_release_gate_report"
            ),
            id="cycle-blocker-missing",
        ),
        pytest.param(
            lambda payload: _cyclic_input_row(
                payload, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]
            ).__setitem__("workspace_matches_source", True),
            id="workspace-match",
        ),
        pytest.param(
            lambda payload: _cyclic_input_row(
                payload, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]
            ).__setitem__("workspace_checksum", "sha256:not-a-digest"),
            id="invalid-checksum",
        ),
        pytest.param(
            lambda payload: payload["source_input_provenance"]["blockers"].remove(
                "input_differs_from_source_commit:"
                + module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2]
            ),
            id="row-blocker-not-listed",
        ),
    ],
)
def test_release_leaf_compare_rejects_cycle_checksum_drift_without_full_guard(
    mutate: Any,
) -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    mutate(stored)
    mutate(rebuilt)

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


@pytest.mark.parametrize(
    "field",
    ["source_checksum", "blocker", "workspace_matches_source"],
)
def test_release_leaf_compare_rejects_other_cyclic_row_tamper(field: str) -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    row = _cyclic_input_row(stored, module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[2])
    row[field] = "tampered" if field != "workspace_matches_source" else True

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


def test_release_leaf_compare_rejects_noncyclic_workspace_checksum_tamper() -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    cyclic_inputs = module.POST_MAIN_RELEASE_EVIDENCE_CYCLIC_WORKSPACE_CHECKSUM_INPUTS[
        relative
    ]
    row = next(
        item
        for item in stored["source_input_provenance"]["inputs"]
        if item.get("path") not in cyclic_inputs
        and isinstance(item.get("workspace_checksum"), str)
    )
    row["workspace_checksum"] = "sha256:" + "e" * 64

    assert not module._release_leaf_payload_matches_replay(
        stored=stored,
        rebuilt=rebuilt,
        relative=relative,
    )


def test_materialize_preserves_only_guarded_cycle_checksums_and_timestamp(
    tmp_path: Path,
) -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    stored["generated_at"] = "2026-08-30T00:00:00+00:00"
    rebuilt["generated_at"] = "2026-08-30T01:00:00+00:00"
    original_rebuilt = json.loads(json.dumps(rebuilt))

    module._materialize_rebuilt_release_leaf(
        replay_root=tmp_path,
        relative=relative,
        stored=stored,
        rebuilt=rebuilt,
    )

    materialized = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    assert materialized["generated_at"] == stored["generated_at"]
    for (
        cyclic_input
    ) in module.POST_MAIN_RELEASE_EVIDENCE_CYCLIC_WORKSPACE_CHECKSUM_INPUTS[relative]:
        assert (
            _cyclic_input_row(materialized, cyclic_input)["workspace_checksum"]
            == _cyclic_input_row(stored, cyclic_input)["workspace_checksum"]
        )
    assert rebuilt == original_rebuilt


def test_materialize_does_not_preserve_cycle_checksums_without_full_guard(
    tmp_path: Path,
) -> None:
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    stored = _guarded_cyclic_pm_payload(
        action_checksum_character="a",
        closure_checksum_character="b",
    )
    rebuilt = _guarded_cyclic_pm_payload(
        action_checksum_character="c",
        closure_checksum_character="d",
    )
    stored["provenance_guard"]["dependency_dag_repaired"] = True
    rebuilt["provenance_guard"]["dependency_dag_repaired"] = True

    module._materialize_rebuilt_release_leaf(
        replay_root=tmp_path,
        relative=relative,
        stored=stored,
        rebuilt=rebuilt,
    )

    materialized = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    for (
        cyclic_input
    ) in module.POST_MAIN_RELEASE_EVIDENCE_CYCLIC_WORKSPACE_CHECKSUM_INPUTS[relative]:
        assert (
            _cyclic_input_row(materialized, cyclic_input)["workspace_checksum"]
            == _cyclic_input_row(rebuilt, cyclic_input)["workspace_checksum"]
        )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_isolated_release_leaf_replay_replaces_output_without_mutating_source(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    relative = module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS[1]
    source_path = tmp_path / relative
    stored = {
        "schema_version": "fixture.v1",
        "generated_at": "2026-08-28T00:00:00+00:00",
        "release_allowed": False,
    }
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(module._canonical_json_bytes(stored))
    _write(tmp_path / "tracked-input.txt", "source\n")
    _git(tmp_path, "add", relative, "tracked-input.txt")
    _git(tmp_path, "commit", "-m", "fixture")
    original = source_path.read_bytes()
    rebuilt = {**stored, "release_allowed": True}

    with module._isolated_release_leaf_replay_root(tmp_path) as replay_root:
        assert (replay_root / "tracked-input.txt").read_text(encoding="utf-8") == (
            "source\n"
        )
        assert module._git_head(replay_root) == module._git_head(tmp_path)
        module._materialize_rebuilt_release_leaf(
            replay_root=replay_root,
            relative=relative,
            stored=stored,
            rebuilt=rebuilt,
        )
        assert json.loads((replay_root / relative).read_text(encoding="utf-8")) == (
            rebuilt
        )
        assert source_path.read_bytes() == original

    assert source_path.read_bytes() == original


def _frontend_git_binding_fixture(root: Path) -> dict[str, object]:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    package_bytes = b'{"name":"fixture"}\n'
    lock_bytes = b'{"lockfileVersion":3}\n'
    (root / "package.json").write_bytes(package_bytes)
    (root / "package-lock.json").write_bytes(lock_bytes)
    _git(root, "add", "package.json", "package-lock.json")
    _git(root, "commit", "-m", "code")
    source_sha = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    for relative in module.EVIDENCE_OUTPUT_ONLY_PATHS:
        _write(root / relative, f"generated:{relative}\n")
    _git(root, "add", *sorted(module.EVIDENCE_OUTPUT_ONLY_PATHS))
    _git(root, "commit", "-m", "evidence")
    return {
        "source": {"commit_sha": source_sha, "tree_sha": source_tree},
        "inputs": {
            "package_json": {
                "bytes": len(package_bytes),
                "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
            },
            "package_lock": {
                "bytes": len(lock_bytes),
                "sha256": "sha256:" + hashlib.sha256(lock_bytes).hexdigest(),
            },
        },
    }


def test_frontend_report_git_binding_requires_real_parent_tree_blobs_and_output_only_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))

    assert module._validate_frontend_report_git_binding(tmp_path, payload) == []

    forged = json.loads(json.dumps(payload))
    forged["source"]["commit_sha"] = "f" * 40
    assert module._validate_frontend_report_git_binding(tmp_path, forged) == [
        "frontend_audit_source_commit_object_missing"
    ]


def test_frontend_report_git_binding_rejects_non_output_evidence_commit(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    _write(tmp_path / "scripts/forged.py", "forged\n")
    _git(tmp_path, "add", "scripts/forged.py")
    _git(tmp_path, "commit", "--amend", "--no-edit")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_evidence_commit_not_output_only" in violations


def test_frontend_report_git_binding_allows_two_parent_merge_after_evidence(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path / "base.txt", "base\n")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "base")
    base_branch = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    _git(tmp_path, "checkout", "-b", "reviewed-feature")
    package_bytes = b'{"name":"fixture"}\n'
    lock_bytes = b'{"lockfileVersion":3}\n'
    (tmp_path / "package.json").write_bytes(package_bytes)
    (tmp_path / "package-lock.json").write_bytes(lock_bytes)
    _git(tmp_path, "add", "package.json", "package-lock.json")
    _git(tmp_path, "commit", "-m", "reviewed source")
    source_sha = _git(tmp_path, "rev-parse", "HEAD")
    source_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    for relative in module.EVIDENCE_OUTPUT_ONLY_PATHS:
        _write(tmp_path / relative, f"generated:{relative}\n")
    _git(tmp_path, "add", *sorted(module.EVIDENCE_OUTPUT_ONLY_PATHS))
    _git(tmp_path, "commit", "-m", "reviewed evidence")
    evidence_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", base_branch)
    _write(tmp_path / "integration.txt", "integration head\n")
    _git(tmp_path, "add", "integration.txt")
    _git(tmp_path, "commit", "-m", "integration change")
    _git(tmp_path, "merge", "--no-ff", "reviewed-feature", "-m", "GitHub merge")
    merge_tokens = _git(tmp_path, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(merge_tokens) == 3
    assert evidence_sha in merge_tokens[1:]
    payload = {
        "source": {"commit_sha": source_sha, "tree_sha": source_tree},
        "inputs": {
            "package_json": {
                "bytes": len(package_bytes),
                "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
            },
            "package_lock": {
                "bytes": len(lock_bytes),
                "sha256": "sha256:" + hashlib.sha256(lock_bytes).hexdigest(),
            },
        },
    }
    assert module._validate_frontend_report_git_binding(tmp_path, payload) == []


def test_frontend_report_git_binding_rejects_uncommitted_self_asserted_report(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    report = tmp_path / module.RELEASE_LEAF_OUTPUTS[4]
    report.write_text("self-asserted replacement\n", encoding="utf-8")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_report_differs_from_evidence_commit" in violations


def test_frontend_report_git_binding_rejects_merge_commit_as_evidence(
    tmp_path: Path,
) -> None:
    payload = _frontend_git_binding_fixture(tmp_path)
    evidence_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-b", "other", evidence_sha)
    _write(tmp_path / "other.txt", "other\n")
    _git(tmp_path, "add", "other.txt")
    _git(tmp_path, "commit", "-m", "other")
    _git(tmp_path, "checkout", "-b", "merge-evidence", evidence_sha)
    report = tmp_path / module.RELEASE_LEAF_OUTPUTS[4]
    report.write_text("replacement evidence\n", encoding="utf-8")
    _git(tmp_path, "add", module.RELEASE_LEAF_OUTPUTS[4])
    _git(tmp_path, "commit", "-m", "replacement")
    _git(tmp_path, "merge", "--no-ff", "other", "-m", "invalid evidence merge")
    # Make the two-parent merge itself the last modifier of the report.
    report.write_text("merge evidence\n", encoding="utf-8")
    _git(tmp_path, "add", module.RELEASE_LEAF_OUTPUTS[4])
    _git(tmp_path, "commit", "--amend", "--no-edit")

    violations = module._validate_frontend_report_git_binding(tmp_path, payload)

    assert "frontend_audit_evidence_commit_not_single_parent" in violations


def _dag(path: Path) -> Path:
    paths = module.EXPECTED_NODE_PATHS
    dag = {
        "schema_version": "generated-artifact-dag.v1",
        "nodes": [
            {
                "id": "capability-registry",
                "kind": "source",
                "dependencies": [],
                "inputs": list(paths["capability-registry"]["inputs"]),
                "outputs": list(paths["capability-registry"]["outputs"]),
            },
            {
                "id": "generated-capability-surfaces",
                "kind": "generated",
                "dependencies": ["capability-registry"],
                "inputs": list(paths["generated-capability-surfaces"]["inputs"]),
                "outputs": list(paths["generated-capability-surfaces"]["outputs"]),
            },
            {
                "id": "verification-receipts",
                "kind": "receipt",
                "dependencies": ["generated-capability-surfaces"],
                "inputs": list(paths["verification-receipts"]["inputs"]),
                "outputs": list(paths["verification-receipts"]["outputs"]),
            },
            {
                "id": "product-state",
                "kind": "product-state",
                "dependencies": ["verification-receipts"],
                "inputs": list(paths["product-state"]["inputs"]),
                "outputs": list(paths["product-state"]["outputs"]),
            },
        ],
    }
    path.write_text(json.dumps(dag), encoding="utf-8")
    return path


def _legacy_dag(path: Path) -> Path:
    _dag(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    receipts = payload["nodes"][2]
    product_state = payload["nodes"][3]
    legacy_receipt_paths = module.LEGACY_EXPECTED_NODE_PATHS["verification-receipts"]
    legacy_product_state_paths = module.LEGACY_EXPECTED_NODE_PATHS["product-state"]
    receipts["inputs"] = list(legacy_receipt_paths["inputs"])
    receipts["outputs"] = list(legacy_receipt_paths["outputs"])
    product_state["inputs"] = list(legacy_product_state_paths["inputs"])
    product_state["outputs"] = list(legacy_product_state_paths["outputs"])
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _complete_repo(root: Path) -> None:
    names = {
        name
        for paths in module.EXPECTED_NODE_PATHS.values()
        for field in ("inputs", "outputs")
        for name in paths[field]
    }
    for name in names:
        _write(root / name, name)


def _write_minimal_capability_registry(root: Path) -> None:
    evidence_path = "artifacts/manifests/test-capability-evidence.json"
    _write(root / evidence_path, "{}\n")
    payload = {
        "schema_version": "structural-analysis-capabilities.v2",
        "authority_rules": {
            "solver_truth_owner": "structural_analysis_core",
            "workbench_truth_owner": "none",
            "ai_truth_owner": "none",
            "fallback_promotion_allowed": False,
            "implemented_does_not_imply_public": True,
            "candidate_result_authority_does_not_imply_release_eligibility": True,
            "release_requires_external_vv_level": 1,
            "release_requires_public": True,
        },
        "current_state_authority": {
            "profile": "exact-current-ci-artifact.v1",
            "workflow": ".github/workflows/product-state-current.yml",
            "manifest": "artifacts/manifests/product_state.current.v1.json",
            "artifact_name_pattern": (
                "product-state-current-{conclusion}-{source_sha}"
            ),
            "source_binding": "exact_commit_sha",
            "attestation_required": True,
            "tracked_snapshots": "historical_only",
            "tracked_self_sha_authority": False,
            "volatile_counts_allowed_in_registry": False,
        },
        "capabilities": [
            {
                "id": "test.blocked",
                "title": "Test blocked capability",
                "status": "blocked",
                "representable": False,
                "implemented": False,
                "executable": False,
                "public": False,
                "numerical_authority": "none",
                "recovery_authority": "none",
                "external_vv_level": 0,
                "release_eligible": False,
                "authority": "none",
                "profile": "test-only",
                "interfaces": ["none"],
                "limitations": ["test-only"],
                "evidence": [evidence_path],
                "runtime_artifacts": [],
            }
        ],
    }
    _write(
        root / "artifacts/manifests/capabilities.yaml",
        json.dumps(payload),
    )


def _fixture_nodes(root: Path) -> list[dict[str, object]]:
    return module.load_dag(_dag(root / "dag.json"))


def _current_bindings(*, candidate: bool = False) -> dict[str, dict[str, object]]:
    bindings = {
        node_id: module._current_binding(node_id)
        for node_id in module.EXPECTED_NODE_ORDER
    }
    if candidate:
        bindings["product-state"] = module._current_binding(
            "product-state",
            violations=["candidate_scope_excludes_product_state"],
            out_of_scope=True,
        )
    return bindings


def _evaluate(
    candidate: dict[str, object],
    baseline: dict[str, object] | None,
) -> dict[str, object]:
    return module.evaluate_snapshot(
        candidate,
        baseline,
        current_bindings=_current_bindings(
            candidate=candidate.get("state_kind") == module.CANDIDATE_STATE
        ),
    )


def test_checked_in_dag_has_required_end_to_end_order() -> None:
    nodes = module.load_dag(ROOT / "canonical/generated-artifact-dag.v1.json")

    assert [node["id"] for node in nodes] == [
        "capability-registry",
        "generated-capability-surfaces",
        "verification-receipts",
        "product-state",
    ]
    assert nodes[1]["dependencies"] == ["capability-registry"]
    assert set(nodes[2]["inputs"]) >= {
        "canonical/canonical-project-wheel-contract.v1.schema.json",
        "canonical/canonical-verification-receipt.v1.schema.json",
        "scripts/build_canonical_project_wheel.py",
        "scripts/build_canonical_verification_receipt.py",
        "scripts/verify_bounded_planar_wheel_smoke.py",
        "scripts/build_runtime_packaging_manifest.py",
    }
    assert set(nodes[2]["inputs"]).isdisjoint(module.POST_MAIN_RELEASE_EVIDENCE_INPUTS)
    assert nodes[2]["outputs"][:3] == [
        "artifacts/manifests/canonical_verification_environment.current.v1.json",
        ".ci/canonical-project-wheel-contract.json",
        ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl",
    ]
    assert set(nodes[2]["outputs"][3:]) == set(module.RUNTIME_RELEASE_LEAF_OUTPUTS)
    assert set(nodes[2]["outputs"]).isdisjoint(
        module.POST_MAIN_RELEASE_EVIDENCE_OUTPUTS
    )
    assert nodes[-1]["dependencies"] == ["verification-receipts"]
    assert nodes[-1]["inputs"] == [
        "canonical/product-state.current.v1.schema.json",
        "scripts/build_product_state.py",
        "canonical/post-main-evidence-overlay.v1.schema.json",
        "canonical/nonpromotion-authority-key-policy.v1.json",
        "scripts/build_post_main_evidence_overlay.py",
        "scripts/nonpromotion_authority_policy.py",
        "scripts/strict_json.py",
    ]


def test_overlay_binding_source_change_invalidates_product_state_only(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    overlay_builder = tmp_path / "scripts/build_post_main_evidence_overlay.py"
    _write(overlay_builder, "changed overlay binding contract")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["product-state"]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert "fingerprint_changed" in report["nodes"]["product-state"]["reasons"]


def test_release_leaf_change_invalidates_receipts_and_product_state(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    sbom_path = tmp_path / "implementation/phase1/runtime_sbom.json"
    _write(sbom_path, "stale runtime SBOM")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["verification-receipts"]["status"] == "stale"
    assert "fingerprint_changed" in report["nodes"]["verification-receipts"]["reasons"]


def test_release_leaf_input_hash_validator_rejects_rehashed_stale_dependency(
    tmp_path: Path,
) -> None:
    report_relative = "release/report.json"
    dependency_relative = "release/dependency.json"
    _write(tmp_path / dependency_relative, '{"version":"current"}\n')
    stale_digest = module._sha256_prefixed(tmp_path / dependency_relative)
    _write(
        tmp_path / report_relative,
        json.dumps(
            {
                "schema_version": "test-report.v1",
                "input_checksums": {dependency_relative: stale_digest},
            }
        ),
    )
    _write(tmp_path / dependency_relative, '{"version":"forged"}\n')

    violations = module._validate_report_input_hashes(
        repo_root=tmp_path,
        report_relative=report_relative,
        schema_version="test-report.v1",
        required_inputs=(dependency_relative,),
    )

    assert violations == [
        f"release_leaf_input_hash_mismatch:{report_relative}->{dependency_relative}"
    ]


def test_release_leaf_input_hash_validator_accepts_explicit_fail_closed_workspace_delta(
    tmp_path: Path,
) -> None:
    report_relative = "release/report.json"
    dependency_relative = "release/dependency.json"
    _write(tmp_path / dependency_relative, '{"version":"current"}\n')
    actual = module._sha256_prefixed(tmp_path / dependency_relative)
    source = "sha256:" + "a" * 64
    blocker = f"input_differs_from_source_commit:{dependency_relative}"
    _write(
        tmp_path / report_relative,
        json.dumps(
            {
                "schema_version": "test-report.v1",
                "input_checksums": {dependency_relative: source},
                "source_input_provenance": {
                    "contract_pass": False,
                    "blockers": [blocker],
                    "inputs": [
                        {
                            "path": dependency_relative,
                            "source_checksum": source,
                            "workspace_checksum": actual,
                            "workspace_matches_source": False,
                            "blocker": blocker,
                        }
                    ],
                },
            }
        ),
    )

    assert (
        module._validate_report_input_hashes(
            repo_root=tmp_path,
            report_relative=report_relative,
            schema_version="test-report.v1",
            required_inputs=(dependency_relative,),
        )
        == []
    )


def test_product_state_schema_change_invalidates_product_state_only(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    schema_path = module.EXPECTED_NODE_PATHS["product-state"]["inputs"][0]
    _write(tmp_path / schema_path, "changed schema")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["product-state"]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert "fingerprint_changed" in report["nodes"]["product-state"]["reasons"]


def test_canonical_dag_rejects_removed_required_artifact_path(tmp_path: Path) -> None:
    payload = json.loads(
        (ROOT / "canonical/generated-artifact-dag.v1.json").read_text(encoding="utf-8")
    )
    payload["nodes"][2]["outputs"].pop()
    dag_path = tmp_path / "weakened-dag.json"
    dag_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.load_dag(dag_path)


def test_changed_registry_invalidates_every_downstream_node(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    registry_path = module.EXPECTED_NODE_PATHS["capability-registry"]["inputs"][0]
    _write(tmp_path / registry_path, "semantic change")

    candidate = module.build_snapshot(nodes, repo_root=tmp_path)
    report = _evaluate(candidate, baseline)

    assert report["stale_nodes"] == [
        "capability-registry",
        "generated-capability-surfaces",
        "verification-receipts",
        "product-state",
    ]
    assert report["nodes"]["generated-capability-surfaces"]["reasons"][-1] == (
        "upstream_stale:capability-registry"
    )


def test_receipt_change_only_invalidates_receipt_and_product_state(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    baseline = module.build_snapshot(nodes, repo_root=tmp_path)
    receipt_path = module.EXPECTED_NODE_PATHS["verification-receipts"]["outputs"][0]
    _write(tmp_path / receipt_path, "new receipt")

    report = _evaluate(module.build_snapshot(nodes, repo_root=tmp_path), baseline)

    assert report["stale_nodes"] == ["verification-receipts", "product-state"]
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "fresh"
    assert report["nodes"]["product-state"]["reasons"][-1] == (
        "upstream_stale:verification-receipts"
    )


def test_missing_output_is_stale_even_when_missing_state_was_blessed(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    receipt_path = module.EXPECTED_NODE_PATHS["verification-receipts"]["outputs"][0]
    (tmp_path / receipt_path).unlink()
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path)

    report = _evaluate(snapshot, snapshot)

    assert report["nodes"]["verification-receipts"]["status"] == "stale"
    assert (
        f"missing:{receipt_path}" in report["nodes"]["verification-receipts"]["reasons"]
    )
    assert report["nodes"]["product-state"]["status"] == "stale"


def test_missing_current_binding_cannot_be_self_blessed(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)

    report = module.evaluate_snapshot(snapshot, snapshot)

    assert report["contract_pass"] is False
    assert report["stale_nodes"] == list(module.EXPECTED_NODE_ORDER)
    assert report["nodes"]["capability-registry"]["current_binding"] == (
        module._current_binding(
            "capability-registry",
            violations=["current_binding_result_missing"],
        )
    )


def test_candidate_verification_binding_excludes_post_main_release_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        module, "_validate_capability_registry_binding", lambda repo_root: []
    )
    monkeypatch.setattr(
        module, "_validate_capability_surfaces_binding", lambda repo_root: []
    )
    monkeypatch.setattr(
        module,
        "_validate_product_state_binding",
        lambda repo_root, nightly_workflow_run_event=None: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: ["canonical_or_runtime_stale"],
    )

    def fail_if_called(repo_root: Path) -> list[str]:
        raise AssertionError("candidate must not inspect protected release evidence")

    monkeypatch.setattr(module, "_validate_release_artifact_bindings", fail_if_called)

    bindings = module.validate_current_bindings(repo_root=tmp_path, candidate=True)

    assert bindings["verification-receipts"]["violations"] == [
        "canonical_or_runtime_stale"
    ]


def test_full_verification_binding_includes_post_main_release_evidence_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0
    monkeypatch.setattr(
        module, "_validate_capability_registry_binding", lambda repo_root: []
    )
    monkeypatch.setattr(
        module, "_validate_capability_surfaces_binding", lambda repo_root: []
    )
    monkeypatch.setattr(
        module,
        "_validate_product_state_binding",
        lambda repo_root, nightly_workflow_run_event=None: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: ["canonical_or_runtime_stale", "shared_stale"],
    )

    def full_release(repo_root: Path) -> list[str]:
        nonlocal calls
        calls += 1
        return ["shared_stale", "post_main_release_stale"]

    monkeypatch.setattr(module, "_validate_release_artifact_bindings", full_release)

    bindings = module.validate_current_bindings(repo_root=tmp_path, candidate=False)

    assert bindings["verification-receipts"]["violations"] == [
        "canonical_or_runtime_stale",
        "shared_stale",
        "post_main_release_stale",
    ]
    assert calls == 1


def test_stale_generated_surface_cannot_be_self_blessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import generate_capability_surfaces

    _complete_repo(tmp_path)
    _write_minimal_capability_registry(tmp_path)
    _write(tmp_path / "README.md", "# Test\n")
    generate_capability_surfaces.write_outputs(tmp_path)
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )
    nodes = _fixture_nodes(tmp_path)
    fresh_snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    fresh_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    fresh_report = module.evaluate_snapshot(
        fresh_snapshot,
        fresh_snapshot,
        current_bindings=fresh_bindings,
    )
    assert fresh_report["scope_pass"] is True
    assert fresh_bindings["generated-capability-surfaces"]["contract_pass"] is True

    surface_path = tmp_path / "docs/api-capabilities.md"
    surface_path.write_text(surface_path.read_text() + "stale edit\n", encoding="utf-8")
    stale_snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    stale_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=True,
    )
    report = module.evaluate_snapshot(
        stale_snapshot,
        stale_snapshot,
        current_bindings=stale_bindings,
    )

    assert report["scope_pass"] is False
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "stale"
    assert report["nodes"]["generated-capability-surfaces"]["reasons"] == [
        "current_binding:stale_or_missing:docs/api-capabilities.md"
    ]


def test_tampered_product_state_cannot_be_self_blessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_product_state as product_state_producer

    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {"head_sha": "a" * 40}}))
    for relative in (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    ):
        _write(tmp_path / relative, "{}\n")
    expected_product_state = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": "a" * 40,
        "quality_evidence": {"head_sha": "a" * 40},
    }
    output_path = tmp_path / module.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    _write(
        output_path,
        json.dumps(
            expected_product_state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    monkeypatch.setattr(module, "_git_head", lambda repo_root: "a" * 40)
    monkeypatch.setattr(
        product_state_producer,
        "build_product_state",
        lambda *args, **kwargs: (expected_product_state, {}),
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_registry_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_surfaces_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )
    nodes = _fixture_nodes(tmp_path)
    fresh_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    assert fresh_bindings["product-state"]["contract_pass"] is True

    _write(output_path, json.dumps({**expected_product_state, "status": "forged"}))
    stale_snapshot = module.build_snapshot(nodes, repo_root=tmp_path)
    stale_bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    report = module.evaluate_snapshot(
        stale_snapshot,
        stale_snapshot,
        current_bindings=stale_bindings,
    )

    assert stale_bindings["product-state"]["violations"] == [
        "product_state_exact_rebuild_mismatch"
    ]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert report["contract_pass"] is False


def test_product_state_rebuild_reuses_canonical_relative_receipt_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_product_state as product_state_producer

    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {"head_sha": "a" * 40}}))
    for relative in (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    ):
        _write(tmp_path / relative, "{}\n")
    expected_product_state = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": "a" * 40,
    }
    output_path = tmp_path / module.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    _write(
        output_path,
        json.dumps(
            expected_product_state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    captured: dict[str, object] = {}

    def rebuild(
        *args: object, **kwargs: object
    ) -> tuple[dict[str, object], dict[str, object]]:
        captured.update(kwargs)
        return expected_product_state, {}

    monkeypatch.setattr(module, "_git_head", lambda repo_root: "a" * 40)
    monkeypatch.setattr(product_state_producer, "build_product_state", rebuild)
    overlay_manifest = Path(
        "overlay/post-main-evidence-overlay.seal.json"
    )

    violations = module._validate_product_state_binding(
        tmp_path,
        nightly_workflow_run_event=event_path,
        post_main_overlay_manifest=overlay_manifest,
    )

    assert violations == []
    assert captured["external_vv_code_receipt"] == (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT
    )
    assert captured["external_vv_modal_receipt"] == (
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT
    )
    assert captured["external_vv_clean_runner_summary"] == (
        module.PRODUCT_STATE_CLEAN_RUNNER_SUMMARY
    )
    assert captured["external_vv_same_operator_supplemental_receipt"] == (
        module.PRODUCT_STATE_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
    )
    assert captured["post_main_overlay_manifest"] == overlay_manifest


def test_product_state_rebuild_reports_invalid_overlay_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = tmp_path / "nightly-event.json"
    event.write_text("{}\n", encoding="utf-8")
    output = tmp_path / module.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    output.parent.mkdir(parents=True)
    output.write_text("{}\n", encoding="utf-8")
    for relative in (
        module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT,
        module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT,
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.build_product_state.build_product_state",
        lambda *_args, **_kwargs: (
            {"blockers": ["post_main_overlay_binding_invalid"]},
            {},
        ),
    )
    monkeypatch.setattr(module, "_git_head", lambda _root: "a" * 40)

    assert module._validate_product_state_binding(
        tmp_path,
        nightly_workflow_run_event=event,
        post_main_overlay_manifest=Path(
            "overlay/post-main-evidence-overlay.seal.json"
        ),
    ) == ["product_state_post_main_overlay_binding_invalid"]


def test_full_product_state_binding_fails_when_one_rebuild_input_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_repo(tmp_path)
    event_path = tmp_path / "nightly-event.json"
    _write(event_path, json.dumps({"workflow_run": {}}))
    _write(tmp_path / module.PRODUCT_STATE_EXTERNAL_CODE_RECEIPT, "{}\n")
    monkeypatch.setattr(
        module,
        "_validate_capability_registry_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_capability_surfaces_binding",
        lambda repo_root: [],
    )
    monkeypatch.setattr(
        module,
        "_validate_canonical_artifacts_binding",
        lambda repo_root: [],
    )

    bindings = module.validate_current_bindings(
        repo_root=tmp_path,
        candidate=False,
        product_state_nightly_event=event_path,
    )
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    report = module.evaluate_snapshot(
        snapshot,
        snapshot,
        current_bindings=bindings,
    )

    assert bindings["product-state"]["violations"] == [
        "product_state_rebuild_input_missing:"
        + module.PRODUCT_STATE_EXTERNAL_MODAL_RECEIPT.as_posix()
    ]
    assert report["nodes"]["product-state"]["status"] == "stale"
    assert report["contract_pass"] is False


def test_candidate_state_keeps_main_only_product_state_unavailable(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)

    snapshot = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    report = _evaluate(snapshot, snapshot)

    assert snapshot["state_kind"] == "candidate"
    assert snapshot["evaluated_through"] == "verification-receipts"
    assert {row["status"] for row in snapshot["nodes"]["product-state"]["outputs"]} == {
        "unavailable"
    }
    assert report["evaluation_mode"] == "candidate"
    assert report["scope_pass"] is True
    assert report["contract_pass"] is False
    assert "self-baselined" in report["claim_boundary"]
    assert report["stale_nodes"] == ["product-state"]
    assert report["nodes"]["verification-receipts"]["status"] == "fresh"
    assert report["nodes"]["product-state"]["reasons"] == [
        *(
            f"candidate_unavailable:{path}"
            for path in module.EXPECTED_NODE_PATHS["product-state"]["inputs"]
        ),
        "candidate_unavailable:artifacts/manifests/product_state.current.v1.json",
    ]


def test_candidate_cli_passes_only_the_complete_non_main_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_repo(tmp_path)
    monkeypatch.setattr(
        module,
        "validate_current_bindings",
        lambda **kwargs: _current_bindings(candidate=kwargs["candidate"]),
    )
    dag = _dag(tmp_path / "dag.json")
    state_path = tmp_path / "candidate-state.json"
    report_path = tmp_path / "candidate-report.json"

    exit_code = module.main(
        [
            "--dag",
            str(dag),
            "--repo-root",
            str(tmp_path),
            "--write-candidate-state",
            str(state_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scope_pass"] is True
    assert report["contract_pass"] is False

    surface_path = module.EXPECTED_NODE_PATHS["generated-capability-surfaces"][
        "outputs"
    ][0]
    (tmp_path / surface_path).unlink()
    exit_code = module.main(
        [
            "--dag",
            str(dag),
            "--repo-root",
            str(tmp_path),
            "--write-candidate-state",
            str(state_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scope_pass"] is False
    assert report["nodes"]["generated-capability-surfaces"]["status"] == "stale"
    assert report["nodes"]["verification-receipts"]["status"] == "stale"


def test_candidate_state_cannot_be_reused_as_trusted_baseline(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    state_path = tmp_path / "candidate-state.json"
    state_path.write_text(module._serialized(candidate), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="cannot be used"):
        module.load_baseline(state_path)


def test_candidate_state_rejects_arbitrary_scope_boundary(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    candidate["evaluated_through"] = "bogus"

    with pytest.raises(module.ArtifactDAGError, match="identify a state node"):
        _evaluate(candidate, candidate)


def test_state_validation_rejects_tampered_fingerprint_chain(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["nodes"]["capability-registry"]["inputs"][0]["sha256"] = "f" * 64

    with pytest.raises(module.ArtifactDAGError, match="state fingerprint is invalid"):
        module.validate_state(state)


def test_state_validation_rejects_removed_canonical_path_after_rehash(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    state = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    receipts = state["nodes"]["verification-receipts"]
    receipts["outputs"].pop()
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.validate_state(state)


def test_state_validation_rejects_non_linear_dependency_bypass(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    receipts = state["nodes"]["verification-receipts"]
    receipts["dependencies"]["capability-registry"] = state["nodes"][
        "capability-registry"
    ]["fingerprint"]
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(module.ArtifactDAGError, match="canonical linear dependency"):
        module.validate_state(state)


def test_legacy_state_receives_full_fail_closed_validation(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["schema_version"] = module.LEGACY_STATE_SCHEMA_VERSION
    state.pop("state_kind")
    state.pop("evaluated_through")
    state["nodes"].pop("verification-receipts")

    with pytest.raises(module.ArtifactDAGError, match="canonical registry-to-product"):
        module.validate_state(state)


def test_legacy_state_accepts_only_the_known_historical_path_revision(
    tmp_path: Path,
) -> None:
    _complete_repo(tmp_path)
    nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    state = module.build_snapshot(nodes, repo_root=tmp_path)
    state["schema_version"] = module.LEGACY_STATE_SCHEMA_VERSION
    state.pop("state_kind")
    state.pop("evaluated_through")

    module.validate_state(state)

    receipts = state["nodes"]["verification-receipts"]
    receipts["inputs"][0]["path"] = "canonical/forged-environment.json"
    identity = {key: value for key, value in receipts.items() if key != "fingerprint"}
    receipts["fingerprint"] = module.hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(module.ArtifactDAGError, match="canonical node paths"):
        module.validate_state(state)


def test_current_schemas_validate_new_and_legacy_v1_payloads(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    nodes = _fixture_nodes(tmp_path)
    snapshot = module.build_snapshot(nodes, repo_root=tmp_path)
    report = _evaluate(snapshot, snapshot)
    state_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-state.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    report_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_state_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-state.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_report_schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    jsonschema.Draft202012Validator(state_schema).validate(snapshot)
    jsonschema.Draft202012Validator(report_schema).validate(report)
    candidate = module.build_snapshot(nodes, repo_root=tmp_path, candidate=True)
    candidate_report = _evaluate(candidate, candidate)
    jsonschema.Draft202012Validator(state_schema).validate(candidate)
    jsonschema.Draft202012Validator(report_schema).validate(candidate_report)

    legacy_nodes = module.load_dag(
        _legacy_dag(tmp_path / "legacy-dag.json"),
        enforce_canonical_paths=False,
    )
    legacy_state = module.build_snapshot(legacy_nodes, repo_root=tmp_path)
    legacy_state["schema_version"] = "generated-artifact-dag-state.v1"
    legacy_state.pop("state_kind")
    legacy_state.pop("evaluated_through")
    module.validate_state(legacy_state)
    jsonschema.Draft202012Validator(legacy_state_schema).validate(legacy_state)
    evaluated_legacy_report = _evaluate(legacy_state, legacy_state)
    jsonschema.Draft202012Validator(report_schema).validate(evaluated_legacy_report)
    assert evaluated_legacy_report["evaluated_through"] == "product-state"

    legacy_report = dict(evaluated_legacy_report)
    legacy_report["schema_version"] = "generated-artifact-dag-report.v1"
    for key in (
        "evaluation_mode",
        "evaluated_through",
        "scope_pass",
        "claim_boundary",
    ):
        legacy_report.pop(key)
    for node in legacy_report["nodes"].values():
        node.pop("current_binding")
    jsonschema.Draft202012Validator(legacy_report_schema).validate(legacy_report)


def test_current_binding_schema_rejects_unbounded_fields(tmp_path: Path) -> None:
    _complete_repo(tmp_path)
    snapshot = module.build_snapshot(_fixture_nodes(tmp_path), repo_root=tmp_path)
    report = _evaluate(snapshot, snapshot)
    report["nodes"]["verification-receipts"]["current_binding"][
        "self_asserted_fresh"
    ] = True
    schema = json.loads(
        (ROOT / "canonical/generated-artifact-dag-report.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_rejects_forward_dependency(tmp_path: Path) -> None:
    path = _dag(tmp_path / "dag.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][0]["dependencies"] = ["product-state"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="topologically ordered"):
        module.load_dag(path)


def test_rejects_product_state_kind_bypass(tmp_path: Path) -> None:
    path = _dag(tmp_path / "dag.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][-1]["kind"] = "source"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.ArtifactDAGError, match="kind must be 'product-state'"):
        module.load_dag(path)
