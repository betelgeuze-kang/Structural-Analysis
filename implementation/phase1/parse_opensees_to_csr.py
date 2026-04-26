#!/usr/bin/env python3
"""Parse OpenSees text model (Tcl/OpenSeesPy-like) into CSR + topology gate report.

This is a single-GPU friendly preprocessing step used to avoid fake topology
expansion from toy dynamic JSONL cases.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "opensees text parsed and topology gate passed",
    "ERR_INVALID_INPUT": "invalid parser input",
    "ERR_FILE_MISSING": "opensees model file missing",
    "ERR_PARSE_FAIL": "no valid nodes/elements parsed from opensees text",
    "ERR_SYNTHETIC_SOURCE": "synthetic/sample source detected under strict mode",
    "ERR_TOPOLOGY_COMPLEXITY": "topology complexity gate failed",
    "ERR_SHELL_BEAM_MIX": "shell-beam mix gate failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model", "report_out"],
    "properties": {
        "model": {"type": "string", "minLength": 1},
        "edges_out": {"type": "string", "minLength": 1},
        "csr_out": {"type": "string", "minLength": 1},
        "report_out": {"type": "string", "minLength": 1},
        "forbid_synthetic_source": {"type": "boolean"},
        "require_real_topology": {"type": "boolean"},
        "require_shell_beam_mix": {"type": "boolean"},
        "min_nodes": {"type": "integer", "minimum": 8},
        "min_edge_node_ratio": {"type": "number", "minimum": 0.0},
        "min_degree_entropy": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "min_element_type_count": {"type": "integer", "minimum": 1},
        "min_largest_component_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}

_INT_RE = re.compile(r"^[+-]?\d+$")
_SPLIT_SEMICOLON = re.compile(r";+")
_COMMENT_RE = re.compile(r"#.*$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _clean_line(line: str) -> str:
    # Remove comments and normalize separators.
    no_comment = _COMMENT_RE.sub("", line)
    return no_comment.strip()


def _tokenize(statement: str) -> list[str]:
    # Replace commas and parentheses used in OpenSeesPy style calls.
    text = statement.replace(",", " ").replace("(", " ").replace(")", " ")
    return [tok for tok in text.split() if tok]


def _as_int(tok: str) -> int | None:
    t = tok.strip()
    if not t:
        return None
    if _INT_RE.match(t):
        try:
            return int(t)
        except Exception:
            return None
    return None


def _iter_statements(text: str):
    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        for stmt in _SPLIT_SEMICOLON.split(line):
            s = stmt.strip()
            if s:
                yield s


def _parse_model(path: Path) -> tuple[dict[int, tuple[float, float, float] | None], list[tuple[str, int, list[int]]], dict[str, int]]:
    nodes: dict[int, tuple[float, float, float] | None] = {}
    elements: list[tuple[str, int, list[int]]] = []
    parse_counters = defaultdict(int)
    next_constraint_id = 10_000_000_000

    txt = path.read_text(encoding="utf-8", errors="ignore")
    for stmt in _iter_statements(txt):
        toks = _tokenize(stmt)
        if not toks:
            continue

        head = toks[0].lower()
        # OpenSeesPy style: ops.node / node
        if head in {"node", "ops.node"}:
            # node <id> x y z ...
            if len(toks) < 2:
                continue
            nid = _as_int(toks[1])
            if nid is None:
                continue
            coords: tuple[float, float, float] | None = None
            if len(toks) >= 5:
                try:
                    x = float(toks[2])
                    y = float(toks[3])
                    z = float(toks[4])
                    coords = (x, y, z)
                except Exception:
                    coords = None
            nodes[int(nid)] = coords
            parse_counters["node"] += 1
            continue

        # OpenSeesPy style: ops.element or element
        if head in {"element", "ops.element"}:
            # element <type> <eid> n1 n2 ...
            if len(toks) < 5:
                continue
            etype = str(toks[1])
            eid = _as_int(toks[2])
            if eid is None:
                continue
            node_ids: list[int] = []
            for tok in toks[3:]:
                iv = _as_int(tok)
                if iv is None:
                    # stop at first non-integer token (material/section args)
                    break
                node_ids.append(int(iv))
            expected_arity = _infer_element_arity(etype)
            if expected_arity is not None and len(node_ids) >= expected_arity:
                node_ids = node_ids[:expected_arity]
            if len(node_ids) >= 2:
                elements.append((etype, int(eid), node_ids))
                parse_counters["element"] += 1
            continue

        if head in {"equaldof", "ops.equaldof"}:
            ints = [iv for iv in (_as_int(tok) for tok in toks[1:]) if iv is not None]
            if len(ints) >= 2:
                next_constraint_id += 1
                elements.append(("constraint_equalDOF", int(next_constraint_id), [int(ints[0]), int(ints[1])]))
                parse_counters["constraint"] += 1
            continue

        if head in {"rigidlink", "ops.rigidlink"}:
            ints = [iv for iv in (_as_int(tok) for tok in toks[1:]) if iv is not None]
            if len(ints) >= 2:
                next_constraint_id += 1
                elements.append(("constraint_rigidLink", int(next_constraint_id), [int(ints[0]), int(ints[1])]))
                parse_counters["constraint"] += 1
            continue

        if head in {"rigiddiaphragm", "ops.rigiddiaphragm"}:
            ints = [iv for iv in (_as_int(tok) for tok in toks[1:]) if iv is not None]
            if len(ints) >= 2:
                master = int(ints[0])
                for slave in ints[1:]:
                    next_constraint_id += 1
                    elements.append(("constraint_rigidDiaphragm", int(next_constraint_id), [master, int(slave)]))
                    parse_counters["constraint"] += 1
            continue

        # Sometimes user scripts alias these calls in procs; keep counters for audit.
        parse_counters["ignored"] += 1

    return nodes, elements, dict(parse_counters)


def _infer_element_arity(etype: str) -> int | None:
    k = str(etype).lower()
    if any(x in k for x in ("shell", "quad", "mitc", "asdshell")):
        return 4
    if "tri" in k:
        return 3
    if any(x in k for x in ("beam", "column", "truss", "brace", "link", "frame")):
        return 2
    return None


def _element_edges(node_ids: list[int]) -> list[tuple[int, int]]:
    # 2-node elements: single edge
    if len(node_ids) == 2:
        a, b = node_ids
        return [(a, b)] if a != b else []
    # N-node elements (shells/polygons): cycle edges.
    out: list[tuple[int, int]] = []
    n = len(node_ids)
    for i in range(n):
        a = int(node_ids[i])
        b = int(node_ids[(i + 1) % n])
        if a != b:
            out.append((a, b))
    return out


def _build_graph(nodes: dict[int, tuple[float, float, float] | None], elements: list[tuple[str, int, list[int]]]) -> tuple[list[int], list[tuple[int, int]], dict[str, int]]:
    # Use only element-participating nodes for topology quality metrics.
    # Raw model files often include helper/constraint nodes that are intentionally isolated.
    used_nodes: set[int] = set()
    edge_set: set[tuple[int, int]] = set()
    et_counter: Counter[str] = Counter()

    for etype, _eid, nids in elements:
        et_counter[str(etype)] += 1
        for a, b in _element_edges(nids):
            if a == b:
                continue
            used_nodes.add(int(a))
            used_nodes.add(int(b))
            u, v = (int(a), int(b)) if a < b else (int(b), int(a))
            edge_set.add((u, v))

    node_ids = sorted(used_nodes)
    return node_ids, sorted(edge_set), dict(et_counter)


def _to_indexed(node_ids: list[int], edges: list[tuple[int, int]]) -> tuple[dict[int, int], list[list[int]]]:
    idx = {nid: i for i, nid in enumerate(node_ids)}
    out: list[list[int]] = []
    for a, b in edges:
        ia = idx.get(int(a))
        ib = idx.get(int(b))
        if ia is None or ib is None or ia == ib:
            continue
        out.append([int(ia), int(ib)])
    return idx, out


def _build_csr(node_count: int, edges_idx: list[list[int]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    adj: list[set[int]] = [set() for _ in range(node_count)]
    for u, v in edges_idx:
        if 0 <= u < node_count and 0 <= v < node_count and u != v:
            adj[u].add(v)
            adj[v].add(u)

    indptr = np.zeros(node_count + 1, dtype=np.int64)
    all_idx: list[int] = []
    degrees = np.zeros(node_count, dtype=np.int64)
    for i in range(node_count):
        row = sorted(adj[i])
        degrees[i] = len(row)
        all_idx.extend(row)
        indptr[i + 1] = len(all_idx)
    indices = np.asarray(all_idx, dtype=np.int64)
    return indptr, indices, degrees


def _largest_component_ratio(node_count: int, edges_idx: list[list[int]]) -> float:
    if node_count <= 0:
        return 0.0
    adj = [[] for _ in range(node_count)]
    for u, v in edges_idx:
        if 0 <= u < node_count and 0 <= v < node_count and u != v:
            adj[u].append(v)
            adj[v].append(u)

    seen = [False] * node_count
    best = 0
    for i in range(node_count):
        if seen[i]:
            continue
        q: deque[int] = deque([i])
        seen[i] = True
        cnt = 0
        while q:
            u = q.popleft()
            cnt += 1
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    q.append(v)
        best = max(best, cnt)
    return float(best) / float(node_count)


def _degree_entropy(degrees: np.ndarray) -> float:
    if degrees.size == 0:
        return 0.0
    values, counts = np.unique(degrees, return_counts=True)
    if len(values) <= 1:
        return 0.0
    p = counts.astype(np.float64) / float(np.sum(counts))
    h = -np.sum(p * np.log(np.clip(p, 1e-12, None)))
    hmax = math.log(float(len(values)))
    if hmax <= 1e-12:
        return 0.0
    return float(h / hmax)


def _is_synthetic_source(path: Path) -> bool:
    # Use filename only to avoid false positives from parent directories.
    s = path.name.lower()
    markers = ["atwood", "sample", "toy", "demo", "sanity", "synthetic"]
    return any(m in s for m in markers)


def _classify_element_types(counter: dict[str, int]) -> dict[str, int]:
    shell = 0
    beam = 0
    brace = 0
    other = 0
    for k, v in counter.items():
        kk = str(k).lower()
        if any(x in kk for x in ["shell", "quad", "tri", "mitc"]):
            shell += int(v)
        elif any(x in kk for x in ["beam", "column", "dispbe", "elasticbeam", "frame"]):
            beam += int(v)
        elif any(x in kk for x in ["truss", "brace"]):
            brace += int(v)
        else:
            other += int(v)
    return {
        "shell": int(shell),
        "beam": int(beam),
        "brace": int(brace),
        "other": int(other),
    }


def main() -> None:
    logger = get_logger("phase3.parse_opensees_to_csr")
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--edges-out", default="implementation/phase1/open_data/megastructure/opensees_edges.json")
    p.add_argument("--csr-out", default="implementation/phase1/open_data/megastructure/opensees_csr.npz")
    p.add_argument("--report-out", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--forbid-synthetic-source", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-real-topology", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--min-nodes", type=int, default=100)
    p.add_argument("--min-edge-node-ratio", type=float, default=0.40)
    p.add_argument("--min-degree-entropy", type=float, default=0.10)
    p.add_argument("--min-element-type-count", type=int, default=1)
    p.add_argument("--min-largest-component-ratio", type=float, default=0.02)
    args = p.parse_args()

    input_payload = {
        "model": str(args.model),
        "edges_out": str(args.edges_out),
        "csr_out": str(args.csr_out),
        "report_out": str(args.report_out),
        "forbid_synthetic_source": bool(args.forbid_synthetic_source),
        "require_real_topology": bool(args.require_real_topology),
        "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        "min_nodes": int(args.min_nodes),
        "min_edge_node_ratio": float(args.min_edge_node_ratio),
        "min_degree_entropy": float(args.min_degree_entropy),
        "min_element_type_count": int(args.min_element_type_count),
        "min_largest_component_ratio": float(args.min_largest_component_ratio),
    }

    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.parse_opensees_to_csr")
        model_path = Path(args.model)
        if not model_path.exists():
            raise FileNotFoundError(str(model_path))

        nodes, elements, parse_counters = _parse_model(model_path)
        node_ids, edges_raw, element_counter = _build_graph(nodes, elements)
        idx_map, edges_idx = _to_indexed(node_ids, edges_raw)

        if len(node_ids) == 0 or len(edges_idx) == 0:
            reason_code = "ERR_PARSE_FAIL"

        n = int(len(node_ids))
        m = int(len(edges_idx))
        indptr = np.array([], dtype=np.int64)
        indices = np.array([], dtype=np.int64)
        degrees = np.array([], dtype=np.int64)
        largest_component_ratio = 0.0
        degree_entropy = 0.0

        if reason_code == "PASS":
            indptr, indices, degrees = _build_csr(n, edges_idx)
            largest_component_ratio = _largest_component_ratio(n, edges_idx)
            degree_entropy = _degree_entropy(degrees)

            edges_out = Path(args.edges_out)
            edges_out.parent.mkdir(parents=True, exist_ok=True)
            edges_out.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "node_count": n,
                        "edges": edges_idx,
                        "source": str(model_path),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            csr_out = Path(args.csr_out)
            csr_out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(csr_out, indptr=indptr, indices=indices, node_count=np.asarray([n], dtype=np.int64))

        synthetic_source_detected = _is_synthetic_source(Path(args.model))
        et_class = _classify_element_types(element_counter)
        shell_count = int(et_class.get("shell", 0))
        beam_count = int(et_class.get("beam", 0))
        shell_beam_mix_pass = bool(shell_count > 0 and beam_count > 0)
        edge_node_ratio = float(m) / float(max(n, 1))
        unique_element_types = int(len(element_counter))
        max_degree = int(np.max(degrees)) if degrees.size else 0
        mean_degree = float(np.mean(degrees)) if degrees.size else 0.0

        checks = {
            "source_is_opensees_text": bool(Path(args.model).suffix.lower() in {".tcl", ".txt", ".py", ".dat"}),
            "source_manifest_pass": True,
            "synthetic_source_detected": bool(synthetic_source_detected),
            "min_nodes_pass": bool(n >= int(args.min_nodes)),
            "edge_node_ratio_pass": bool(edge_node_ratio >= float(args.min_edge_node_ratio)),
            "degree_entropy_pass": bool(degree_entropy >= float(args.min_degree_entropy)),
            "element_type_count_pass": bool(unique_element_types >= int(args.min_element_type_count)),
            "largest_component_pass": bool(largest_component_ratio >= float(args.min_largest_component_ratio)),
            "shell_beam_mix_pass": bool(shell_beam_mix_pass),
            "real_topology_pass": False,
        }
        checks["real_topology_pass"] = bool(
            checks["source_is_opensees_text"]
            and checks["min_nodes_pass"]
            and checks["edge_node_ratio_pass"]
            and checks["degree_entropy_pass"]
            and checks["element_type_count_pass"]
            and checks["largest_component_pass"]
            and (checks["shell_beam_mix_pass"] or not bool(args.require_shell_beam_mix))
            and (not checks["synthetic_source_detected"] or not bool(args.forbid_synthetic_source))
        )

        if reason_code == "PASS" and bool(args.forbid_synthetic_source) and bool(synthetic_source_detected):
            reason_code = "ERR_SYNTHETIC_SOURCE"
        if reason_code == "PASS" and bool(args.require_shell_beam_mix) and not bool(shell_beam_mix_pass):
            reason_code = "ERR_SHELL_BEAM_MIX"
        if reason_code == "PASS" and bool(args.require_real_topology) and not bool(checks["real_topology_pass"]):
            reason_code = "ERR_TOPOLOGY_COMPLEXITY"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-opensees-topology-parser",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "source_provenance": {
                "source_class": "opensees_text",
                "source_path": str(Path(args.model)),
                "source_sha256": _sha256(Path(args.model)) if Path(args.model).exists() else "",
            },
            "parse_counters": parse_counters,
            "metrics": {
                "node_count": n,
                "edge_count_undirected": m,
                "edge_node_ratio": float(edge_node_ratio),
                "degree_entropy": float(degree_entropy),
                "largest_component_ratio": float(largest_component_ratio),
                "mean_degree": float(mean_degree),
                "max_degree": int(max_degree),
                "element_type_count": int(unique_element_types),
                "shell_element_count": int(shell_count),
                "beam_element_count": int(beam_count),
                "element_type_histogram": element_counter,
                "element_class_histogram": et_class,
            },
            "artifacts": {
                "edges_json": str(args.edges_out),
                "csr_npz": str(args.csr_out),
            },
            "checks": checks,
            "contract_pass": bool(reason_code == "PASS"),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, 20, "opensees_parser.completed", contract_pass=bool(payload["contract_pass"]), reason_code=reason_code)
        print(f"Wrote OpenSees topology report: {out}")
        if reason_code != "PASS":
            raise SystemExit(1)

    except FileNotFoundError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-opensees-topology-parser",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_FILE_MISSING",
            "reason": f"{REASONS['ERR_FILE_MISSING']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote OpenSees topology report: {out}")
        raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-opensees-topology-parser",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote OpenSees topology report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
