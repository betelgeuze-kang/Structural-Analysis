#!/usr/bin/env python3
"""Fixed-coefficient graph heuristic for the legacy LF -> GNN assist path.

Design goals:
- Preserve O(N+E) runtime with bounded message passes.
- Propose displacement corrections from an internal scalar contraction.
- Keep mobile/web fallback compatibility (no mandatory torch dependency).

Mobile/static contract notes:
- ``run_one_batch`` and ``run_one_batch_with_metrics`` are compatibility
  entrypoints for the LF->GNN residual-correction assist surface;
- this module does not claim autonomous solver truth;
- the canonical mobile/static handoff is recorded in
  ``mobile-static-contracts.md`` and mirrored by the constants below.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

MODEL_API_VERSION = "1.2.0"
EPS = 1e-12
MOBILE_STATIC_CONTRACT_REF = "implementation/phase1/mobile-static-contracts.md#a1-lf---gnn-interface-contract"
CLAIM_BOUNDARY = "residual_correction_assist_not_solver_truth"
LF_GNN_MODEL_ENTRYPOINTS = ("run_one_batch", "run_one_batch_with_metrics")
LF_GNN_STANDARD_REASON_CODES = {
    "PASS": "input/output contract is satisfied",
    "ERR_LF_GNN_FIELD_MISSING": "required field is absent",
    "ERR_LF_GNN_TYPE": "field exists but has wrong type",
    "ERR_LF_GNN_EMPTY_BATCH": "node/edge/LF batch is empty",
    "ERR_LF_GNN_SHAPE_MISMATCH": "node, edge, or LF response dimensions are inconsistent",
    "ERR_LF_GNN_ACCURACY_BELOW_TARGET": "residual correction did not meet the configured accuracy target",
    "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE": "corrected state has not been re-evaluated by a physics solver",
    "ERR_LF_GNN_COMPLEXITY_GUARDRAIL": "observed operation budget exceeded the linear-complexity guardrail",
    "ERR_LF_GNN_UNSUPPORTED_FEATURE": "feature family is outside the residual model scope",
    "ERR_LF_GNN_CLAIM_BOUNDARY": "output tries to claim autonomous solver truth",
}
LF_GNN_REQUIRED_BATCH_ARGUMENTS = ("nodes", "edges", "meta", "gain")
LF_GNN_REQUIRED_NODE_FIELDS = ("node_id", "ux", "uy", "uz")
LF_GNN_OPTIONAL_NODE_FIELDS = ("f_norm", "rx", "ry", "rz", "bc_type")
LF_GNN_REQUIRED_EDGE_FIELDS = ("from", "to")


def _contract_metrics() -> dict[str, Any]:
    return {
        "model_api_version": MODEL_API_VERSION,
        "mobile_static_contract_ref": MOBILE_STATIC_CONTRACT_REF,
        "claim_boundary": CLAIM_BOUNDARY,
        "algorithm_kind": "fixed_coefficient_graph_heuristic",
        "learned_parameters": False,
        "solver_recomputed": False,
        "physical_metrics_status": "unavailable",
        "physical_metrics_reason_code": "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE",
        # Retain the legacy metric keys, but do not substitute contraction of
        # internal scalars for a residual evaluated at the proposed state.
        "residual_l1_before": None,
        "residual_l1_after": None,
        "residual_reduction_ratio": None,
        "physical_accuracy_pct": None,
        "target_accuracy_pct": 99.9,
        "target_met": False,
        "standard_reason_codes": LF_GNN_STANDARD_REASON_CODES,
        "entrypoints": list(LF_GNN_MODEL_ENTRYPOINTS),
        "required_batch_arguments": list(LF_GNN_REQUIRED_BATCH_ARGUMENTS),
        "required_node_fields": list(LF_GNN_REQUIRED_NODE_FIELDS),
        "optional_node_fields": list(LF_GNN_OPTIONAL_NODE_FIELDS),
        "required_edge_fields": list(LF_GNN_REQUIRED_EDGE_FIELDS),
    }


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _norm3(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _normalize3(x: float, y: float, z: float) -> tuple[float, float, float]:
    n = _norm3(x, y, z)
    if n <= EPS:
        t = 1.0 / math.sqrt(3.0)
        return t, t, t
    return x / n, y / n, z / n


def _build_node_index(nodes: list[dict]) -> tuple[list[str], dict[str, int]]:
    node_ids: list[str] = []
    index: dict[str, int] = {}
    for i, row in enumerate(nodes):
        node_id = str(row.get("node_id", f"N{i + 1}"))
        node_ids.append(node_id)
        index[node_id] = i
    return node_ids, index


def _build_undirected_adjacency(node_index: dict[str, int], edges: list[dict]) -> list[list[int]]:
    adj_sets: list[set[int]] = [set() for _ in range(len(node_index))]
    for edge in edges:
        u_id = str(edge.get("from", ""))
        v_id = str(edge.get("to", ""))
        if u_id not in node_index or v_id not in node_index:
            continue
        u = node_index[u_id]
        v = node_index[v_id]
        if u == v:
            continue
        adj_sets[u].add(v)
        adj_sets[v].add(u)
    return [sorted(list(nei)) for nei in adj_sets]


def _neighbor_mean(values: list[float], adjacency: list[list[int]]) -> list[float]:
    out = [0.0 for _ in values]
    for i, nbrs in enumerate(adjacency):
        if not nbrs:
            out[i] = values[i]
            continue
        out[i] = sum(values[j] for j in nbrs) / len(nbrs)
    return out


def _edge_count_undirected(adjacency: list[list[int]]) -> int:
    return sum(len(nbrs) for nbrs in adjacency) // 2


@dataclass
class GNNResidualModel:
    """Historical API name; no trained GNN or physical residual operator is used."""

    # These fixed coefficients contract internal scalars; they do not establish
    # stability or equilibrium of the proposed displacement state.
    gain_self: float = 0.86
    gain_neighbor: float = 0.13
    damping: float = 1.0
    message_passes: int = 4
    residual_to_disp_scale: float = 0.001
    direction_mix: float = 0.85
    residual_clip: float = 1e9

    def _residual_scalar(self, row: dict) -> float:
        if "f_norm" in row:
            return max(0.0, _safe_float(row.get("f_norm", 0.0)))
        rx = _safe_float(row.get("rx", 0.0))
        ry = _safe_float(row.get("ry", 0.0))
        rz = _safe_float(row.get("rz", 0.0))
        return max(0.0, _norm3(rx, ry, rz))

    def _boundary_fixed(self, row: dict) -> bool:
        bc = str(row.get("bc_type", "")).lower()
        return bc in {"fixed", "pin-fixed", "clamped"}

    def forward_with_metrics(self, nodes: list[dict], edges: list[dict], meta: dict) -> tuple[list[dict], dict]:
        """Return corrected nodes plus review metrics for one residual-correction batch.

        Expected argument contract is intentionally simple for mobile/static
        review: ``nodes`` and ``edges`` are list-of-dict payloads, ``meta`` is a
        dict carrying source/unit/provenance context, and ``gain`` is converted
        to the model's residual-to-displacement scale by the public wrapper.
        """
        if not nodes:
            return [], {
                **_contract_metrics(),
                "heuristic_state_l1_before": 0.0,
                "heuristic_state_l1_after": 0.0,
                "heuristic_state_reduction_ratio": 0.0,
                "complexity_class": "O(N+E)",
                "linear_complexity_observed": True,
                "operation_count_estimate": 0,
                "node_count": 0,
                "edge_count": 0,
            }

        node_ids, node_index = _build_node_index(nodes)
        adjacency = _build_undirected_adjacency(node_index=node_index, edges=edges)
        edge_count = _edge_count_undirected(adjacency)

        residual_before = [self._residual_scalar(row) for row in nodes]
        state = residual_before[:]

        # O(message_passes * (N+E)): adjacency traversal and local updates only.
        for _ in range(max(1, int(self.message_passes))):
            neigh = _neighbor_mean(state, adjacency)
            updated: list[float] = []
            for r_self, r_nei in zip(state, neigh):
                correction = self.gain_self * r_self + self.gain_neighbor * r_nei
                r_next = r_self - self.damping * correction
                updated.append(min(self.residual_clip, max(0.0, abs(r_next))))
            state = updated

        residual_after = state
        correction_scalar = [max(0.0, rb - ra) for rb, ra in zip(residual_before, residual_after)]

        isotropic = 1.0 / math.sqrt(3.0)
        corrected: list[dict] = []
        for i, row in enumerate(nodes):
            ux = _safe_float(row.get("ux", 0.0))
            uy = _safe_float(row.get("uy", 0.0))
            uz = _safe_float(row.get("uz", 0.0))

            if self._boundary_fixed(row):
                corrected.append({"node_id": node_ids[i], "ux": ux, "uy": uy, "uz": uz})
                continue

            dx, dy, dz = _normalize3(ux, uy, uz)
            direction_x = self.direction_mix * dx + (1.0 - self.direction_mix) * isotropic
            direction_y = self.direction_mix * dy + (1.0 - self.direction_mix) * isotropic
            direction_z = self.direction_mix * dz + (1.0 - self.direction_mix) * isotropic

            mag = self.residual_to_disp_scale * correction_scalar[i]
            dux = -mag * direction_x
            duy = -mag * direction_y
            duz = -mag * direction_z

            corrected.append(
                {
                    "node_id": node_ids[i],
                    "ux": float(ux + dux),
                    "uy": float(uy + duy),
                    "uz": float(uz + duz),
                }
            )

        before_l1 = float(sum(residual_before))
        after_l1 = float(sum(residual_after))
        reduction_ratio = 0.0 if before_l1 <= EPS else max(0.0, min(1.0, 1.0 - (after_l1 / before_l1)))
        passes = max(1, int(self.message_passes))
        operation_count_estimate = passes * (4 * len(nodes) + 3 * edge_count)
        linear_budget = 128 * (len(nodes) + edge_count + 1)
        linear_complexity_observed = operation_count_estimate <= linear_budget

        metrics = {
            **_contract_metrics(),
            "heuristic_state_l1_before": before_l1,
            "heuristic_state_l1_after": after_l1,
            "heuristic_state_reduction_ratio": reduction_ratio,
            "complexity_class": "O(N+E)",
            "linear_complexity_observed": linear_complexity_observed,
            "operation_count_estimate": int(operation_count_estimate),
            "node_count": len(nodes),
            "edge_count": int(edge_count),
        }
        return corrected, metrics

    def forward(self, nodes: list[dict], edges: list[dict], meta: dict) -> list[dict]:
        corrected, _ = self.forward_with_metrics(nodes, edges, meta)
        return corrected


def run_one_batch(nodes: list[dict], edges: list[dict], meta: dict, gain: float) -> list[dict]:
    """Compatibility contract for LF->GNN interface v1.x.

    This wrapper preserves the legacy output shape: a list of corrected node
    dictionaries. Use ``run_one_batch_with_metrics`` when the caller needs the
    mobile/static contract metadata and claim boundary in the metrics envelope.
    """
    model = GNNResidualModel(residual_to_disp_scale=max(0.0, float(gain)))
    return model.forward(nodes, edges, meta)


def run_one_batch_with_metrics(nodes: list[dict], edges: list[dict], meta: dict, gain: float) -> tuple[list[dict], dict]:
    """Compatibility contract for LF->GNN interface v1.x with metrics.

    Returns a ``(corrected_nodes, metrics)`` tuple. Metrics include
    ``mobile_static_contract_ref`` and ``claim_boundary`` so reports can show
    that residual correction is an assist surface rather than solver truth.
    Legacy physical/residual metric keys are nullable: only the explicitly
    named heuristic-state metrics are available without a solver recompute.
    """
    model = GNNResidualModel(residual_to_disp_scale=max(0.0, float(gain)))
    return model.forward_with_metrics(nodes, edges, meta)
