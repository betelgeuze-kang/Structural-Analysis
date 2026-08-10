from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_material_family_adequacy_audit.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_material_family_adequacy_audit",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _git_object(commit: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        stderr=subprocess.STDOUT,
    )


def _raw_object_is_ancestor(ancestor: str, descendant: str) -> bool:
    pending = [descendant]
    visited: set[str] = set()
    while pending:
        commit = pending.pop()
        if commit in visited:
            continue
        visited.add(commit)
        raw = subprocess.check_output(
            ["git", "cat-file", "-p", commit],
            cwd=ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        )
        header, separator, _ = raw.partition("\n\n")
        assert separator, f"commit object has no header terminator: {commit}"
        lines = header.splitlines()
        assert lines and re.fullmatch(r"tree [0-9a-f]{40}", lines[0])
        if commit == ancestor:
            return True
        for line in lines[1:]:
            if not line.startswith("parent "):
                continue
            parent = line.removeprefix("parent ")
            assert re.fullmatch(r"[0-9a-f]{40}", parent)
            pending.append(parent)
    return False


def test_committed_material_family_audit_preserves_its_recorded_epoch() -> None:
    payload = json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8"))
    module.validate(payload, root=ROOT, current=False)

    recorded_commit = payload["source"]["repository_commit_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", recorded_commit)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert _raw_object_is_ancestor(recorded_commit, head)

    lfs_pointer = re.compile(
        rb"version https://git-lfs.github.com/spec/v1\n"
        rb"oid sha256:([0-9a-f]{64})\n"
        rb"size ([1-9][0-9]*)\n?"
    )
    for path, expected in payload["source"]["input_checksums"].items():
        recorded = _git_object(recorded_commit, path)
        pointer = lfs_pointer.fullmatch(recorded)
        if pointer is None:
            actual = "sha256:" + hashlib.sha256(recorded).hexdigest()
        else:
            actual = "sha256:" + pointer.group(1).decode("ascii")
            hydrated = ROOT / path
            assert hydrated.stat().st_size == int(pointer.group(2))
            assert "sha256:" + hashlib.sha256(hydrated.read_bytes()).hexdigest() == (
                actual
            )
        assert actual == expected, path

    passed, reason = module.check(root=ROOT)
    assert passed is False
    assert reason == (
        "g1_mgt_material_family_adequacy_audit_invalid:"
        "material_family_audit_sources_stale"
    )


def test_material_family_audit_keeps_nonlinear_source_gap_visible() -> None:
    payload = json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["operator_binding"]["all_geometry_arrays_exact"] is True
    assert payload["operator_binding"]["property_fallback_count"] == 0
    assert payload["material_fixture"]["element_count"] == 5_572
    assert payload["material_fixture"]["family_counts"] == {
        "CONC": 2_182,
        "SRC": 1_692,
        "STEEL": 1_692,
        "USER": 6,
    }
    assert payload["accepted_state_audit"]["load_factor"] == 1.0
    assert payload["accepted_state_audit"]["free_equation_count"] == 70_560
    assert payload["source_adequacy"][
        "authoritative_nonlinear_parameter_set_complete"
    ] is False
    assert all(
        payload["source_adequacy"]["missing_authoritative_nonlinear_fields"].values()
    )
    assert payload["claims"][
        "nonlinear_material_family_breadth_connected_to_equilibrium"
    ] is False
    assert payload["claims"]["g1_closure"] is False
