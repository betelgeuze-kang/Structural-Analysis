#!/usr/bin/env python3
"""Fingerprint the product artifact DAG and invalidate stale descendants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAG = ROOT / "canonical/generated-artifact-dag.v1.json"


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


def build_snapshot(nodes: list[dict[str, Any]], *, repo_root: Path) -> dict[str, Any]:
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
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshots[node["id"]] = {**identity, "fingerprint": fingerprint}
    return {"schema_version": "generated-artifact-dag-state.v1", "nodes": snapshots}


def evaluate_snapshot(
    candidate: dict[str, Any], baseline: dict[str, Any] | None
) -> dict[str, Any]:
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
            "fingerprint": node["fingerprint"],
            "reasons": reasons,
        }
    stale = [
        node_id for node_id, node in report_nodes.items() if node["status"] == "stale"
    ]
    return {
        "schema_version": "generated-artifact-dag-report.v1",
        "contract_pass": not stale,
        "stale_nodes": stale,
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
    parser.add_argument("--state", type=Path)
    parser.add_argument("--write-state", type=Path)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if args.state and args.write_state:
        parser.error("--state and --write-state are mutually exclusive")
    nodes = load_dag(args.dag)
    snapshot = build_snapshot(nodes, repo_root=args.repo_root)
    missing = [
        row["path"]
        for node in snapshot["nodes"].values()
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
    report = evaluate_snapshot(snapshot, baseline)
    if args.report:
        _atomic_write(args.report, report)
    print(_serialized(report), end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
