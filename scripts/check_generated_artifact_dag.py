#!/usr/bin/env python3
"""Fingerprint the product artifact DAG and invalidate stale descendants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAG = ROOT / "canonical/generated-artifact-dag.v1.json"
SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class ArtifactDAGError(ValueError):
    """Raised when the artifact DAG contract is malformed."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArtifactDAGError(f"{path}: root must be an object")
    return payload


def _safe_path(value: Any) -> str:
    text = str(value).strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ArtifactDAGError(f"unsafe repository-relative path: {value!r}")
    return path.as_posix()


def _source_sha(value: Any) -> str:
    source_sha = str(value).strip()
    if SOURCE_SHA_PATTERN.fullmatch(source_sha) is None:
        raise ArtifactDAGError("source SHA must be exactly 40 lowercase hex characters")
    return source_sha


def _repository_head_sha(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ArtifactDAGError(
            f"cannot resolve checked-out Git HEAD below {repo_root}"
        ) from exc
    return _source_sha(completed.stdout)


def load_dag(path: Path = DEFAULT_DAG) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != "generated-artifact-dag.v1":
        raise ArtifactDAGError("unsupported artifact DAG schema")
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ArtifactDAGError("nodes must be a non-empty list")
    nodes: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ArtifactDAGError("each node must be an object")
        node_id = str(raw_node.get("id", "")).strip()
        if not node_id or node_id in ids:
            raise ArtifactDAGError(f"invalid or duplicate node id: {node_id!r}")
        ids.add(node_id)
        dependencies = raw_node.get("dependencies")
        inputs = raw_node.get("inputs")
        outputs = raw_node.get("outputs")
        if not all(
            isinstance(value, list) for value in (dependencies, inputs, outputs)
        ):
            raise ArtifactDAGError(
                f"{node_id}: dependencies, inputs, and outputs must be lists"
            )
        nodes.append(
            {
                "id": node_id,
                "kind": str(raw_node.get("kind", "")).strip(),
                "dependencies": [str(item) for item in dependencies],
                "inputs": [_safe_path(item) for item in inputs],
                "outputs": [_safe_path(item) for item in outputs],
            }
        )
    known: set[str] = set()
    for node in nodes:
        unknown = set(node["dependencies"]) - ids
        if unknown:
            raise ArtifactDAGError(
                f"{node['id']}: unknown dependencies {sorted(unknown)}"
            )
        not_yet_seen = set(node["dependencies"]) - known
        if not_yet_seen:
            raise ArtifactDAGError(
                f"{node['id']}: nodes must be topologically ordered; dependencies follow node {sorted(not_yet_seen)}"
            )
        known.add(node["id"])
    if nodes[0]["id"] != "capability-registry" or nodes[-1]["id"] != "product-state":
        raise ArtifactDAGError("DAG must run from capability-registry to product-state")
    return nodes


def _path_identity(repo_root: Path, relative_path: str) -> dict[str, Any]:
    path = repo_root / relative_path
    if not path.is_file():
        return {"path": relative_path, "status": "missing", "sha256": None}
    return {
        "path": relative_path,
        "status": "available",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_snapshot(
    nodes: list[dict[str, Any]], *, repo_root: Path, source_sha: str
) -> dict[str, Any]:
    exact_source_sha = _source_sha(source_sha)
    snapshots: dict[str, dict[str, Any]] = {}
    for node in nodes:
        inputs = [_path_identity(repo_root, path) for path in node["inputs"]]
        outputs = [_path_identity(repo_root, path) for path in node["outputs"]]
        identity = {
            "id": node["id"],
            "kind": node["kind"],
            "dependencies": {
                dependency: snapshots[dependency]["fingerprint"]
                for dependency in node["dependencies"]
            },
            "inputs": inputs,
            "outputs": outputs,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        snapshots[node["id"]] = {**identity, "fingerprint": fingerprint}
    return {
        "schema_version": "generated-artifact-dag-state.v1",
        "source_commit_sha": exact_source_sha,
        "nodes": snapshots,
    }


def _validate_state(payload: dict[str, Any]) -> str:
    if payload.get("schema_version") != "generated-artifact-dag-state.v1":
        raise ArtifactDAGError("unsupported artifact DAG state schema")
    source_sha = _source_sha(payload.get("source_commit_sha"))
    if not isinstance(payload.get("nodes"), dict):
        raise ArtifactDAGError("artifact DAG state nodes must be an object")
    return source_sha


def _required_node_ids(
    candidate: dict[str, Any], require_through: str | None
) -> tuple[list[str], list[str], str]:
    node_ids = list(candidate["nodes"])
    if not node_ids:
        raise ArtifactDAGError("artifact DAG state must contain nodes")
    target = require_through or node_ids[-1]
    if target not in candidate["nodes"]:
        raise ArtifactDAGError(f"unknown --require-through node: {target}")
    target_index = node_ids.index(target)
    return node_ids[: target_index + 1], node_ids[target_index + 1 :], target


def evaluate_snapshot(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    require_through: str | None = None,
) -> dict[str, Any]:
    source_sha = _validate_state(candidate)
    if baseline is not None:
        _validate_state(baseline)
    required_nodes, deferred_nodes, target = _required_node_ids(
        candidate, require_through
    )
    required = set(required_nodes)
    baseline_nodes = baseline.get("nodes", {}) if isinstance(baseline, dict) else {}
    report_nodes: dict[str, dict[str, Any]] = {}
    for node_id, node in candidate["nodes"].items():
        reasons: list[str] = []
        missing = [
            row["path"]
            for row in [*node["inputs"], *node["outputs"]]
            if row["status"] == "missing"
        ]
        if missing:
            reasons.extend(f"missing:{path}" for path in missing)
        previous = (
            baseline_nodes.get(node_id) if isinstance(baseline_nodes, dict) else None
        )
        if not isinstance(previous, dict):
            reasons.append("baseline_missing")
        elif previous.get("fingerprint") != node["fingerprint"]:
            reasons.append("fingerprint_changed")
        stale_dependencies = [
            dependency
            for dependency in node["dependencies"]
            if report_nodes[dependency]["status"] != "fresh"
        ]
        reasons.extend(
            f"upstream_stale:{dependency}" for dependency in stale_dependencies
        )
        report_nodes[node_id] = {
            "status": "stale" if reasons else "fresh",
            "required": node_id in required,
            "fingerprint": node["fingerprint"],
            "reasons": reasons,
        }
    stale = [
        node_id for node_id, node in report_nodes.items() if node["status"] == "stale"
    ]
    required_stale = [node_id for node_id in stale if node_id in required]
    deferred_stale = [node_id for node_id in stale if node_id not in required]
    return {
        "schema_version": "generated-artifact-dag-report.v1",
        "source_commit_sha": source_sha,
        "require_through": target,
        "required_nodes": required_nodes,
        "deferred_nodes": deferred_nodes,
        "contract_pass": not required_stale,
        "stale_nodes": required_stale,
        "deferred_stale_nodes": deferred_stale,
        "nodes": report_nodes,
    }


def _serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dag", type=Path, default=DEFAULT_DAG)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--verify-head",
        action="store_true",
        help="Require --source-sha to equal the checked-out repository HEAD.",
    )
    parser.add_argument("--state", type=Path)
    parser.add_argument("--write-state", type=Path)
    parser.add_argument(
        "--require-through",
        help=(
            "Require the topologically ordered DAG prefix through this node; "
            "later nodes remain visible but do not decide the exit status."
        ),
    )
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if args.state and args.write_state:
        parser.error("--state and --write-state are mutually exclusive")
    exact_source_sha = _source_sha(args.source_sha)
    if args.verify_head:
        observed_head = _repository_head_sha(args.repo_root)
        if observed_head != exact_source_sha:
            print(
                "source SHA does not match checked-out HEAD: "
                f"expected={exact_source_sha} observed={observed_head}",
                file=sys.stderr,
            )
            return 1
    nodes = load_dag(args.dag)
    snapshot = build_snapshot(
        nodes, repo_root=args.repo_root, source_sha=exact_source_sha
    )
    required_nodes, _, _ = _required_node_ids(snapshot, args.require_through)
    required = set(required_nodes)
    missing = [
        row["path"]
        for node_id, node in snapshot["nodes"].items()
        if node_id in required
        for row in [*node["inputs"], *node["outputs"]]
        if row["status"] == "missing"
    ]
    if args.write_state:
        if missing and not args.allow_missing:
            print(
                "refusing to bless missing DAG artifacts: " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1
        _atomic_write(args.write_state, snapshot)
        print(_serialized(snapshot), end="")
        return 0

    baseline = _read_json(args.state) if args.state and args.state.is_file() else None
    report = evaluate_snapshot(snapshot, baseline, require_through=args.require_through)
    if args.report:
        _atomic_write(args.report, report)
    print(_serialized(report), end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
