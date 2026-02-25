#!/usr/bin/env python3
"""Torch residual model with project-style signature for LF->GNN smoke path."""

from __future__ import annotations

from dataclasses import dataclass

MODEL_API_VERSION = "1.0.0"


@dataclass
class GNNResidualModel:
    gain: float = 0.001

    def forward(self, nodes: list[dict], edges: list[dict], meta: dict) -> list[dict]:
        import torch  # type: ignore

        node_ids = [r.get("node_id") for r in nodes]
        u = torch.tensor(
            [[float(r.get("ux", 0.0)), float(r.get("uy", 0.0)), float(r.get("uz", 0.0))] for r in nodes],
            dtype=torch.float32,
        )
        f = torch.tensor([float(r.get("f_norm", 0.0)) for r in nodes], dtype=torch.float32).unsqueeze(1)

        # deterministic linear residual correction (placeholder for real GNN)
        delta = (-self.gain) * f.repeat(1, 3)
        u_final = u + delta

        return [
            {"node_id": node_ids[i], "ux": float(u_final[i, 0]), "uy": float(u_final[i, 1]), "uz": float(u_final[i, 2])}
            for i in range(len(node_ids))
        ]


def run_one_batch(nodes: list[dict], edges: list[dict], meta: dict, gain: float) -> list[dict]:
    """Compatibility contract for LF->GNN interface v1.x.

    Backward-compatible changes (minor): add optional meta fields only.
    Breaking changes (major): modify required node/edge keys or return schema.
    """
    model = GNNResidualModel(gain=gain)
    return model.forward(nodes, edges, meta)
