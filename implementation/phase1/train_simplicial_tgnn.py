#!/usr/bin/env python3
"""Step-3: train simplicial/cellular temporal GNN (higher-order topology)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random


def _require_torch():
    try:
        import torch  # type: ignore
        import torch.nn.functional as F  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"torch is required: {exc}")
    return torch, F


from spatiotemporal_dataset_utils import load_jsonl  # noqa: E402


REASONS = {
    "PASS": "simplicial temporal gnn trained with higher-order topology",
    "ERR_DATASET_EMPTY": "dataset is empty",
    "ERR_METRIC_FAIL": "validation metric gate failed",
}


class SimplicialTemporalGNN:
    def __init__(self, torch, node_feat_dim: int, hidden_dim: int):
        nn = torch.nn
        self.in_proj = nn.Linear(node_feat_dim + 2, hidden_dim)
        self.self_proj = nn.Linear(hidden_dim, hidden_dim)
        self.nei_proj = nn.Linear(hidden_dim, hidden_dim)
        self.face_proj = nn.Linear(hidden_dim, hidden_dim)
        self.gru = nn.GRUCell(hidden_dim, hidden_dim)
        self.out_proj = nn.Linear(hidden_dim, 1)
        self._modules = [self.in_proj, self.self_proj, self.nei_proj, self.face_proj, self.gru, self.out_proj]

    def parameters(self):
        for m in self._modules:
            for p in m.parameters():
                yield p

    def state_dict(self):
        return {
            "in_proj": self.in_proj.state_dict(),
            "self_proj": self.self_proj.state_dict(),
            "nei_proj": self.nei_proj.state_dict(),
            "face_proj": self.face_proj.state_dict(),
            "gru": self.gru.state_dict(),
            "out_proj": self.out_proj.state_dict(),
        }

    def to(self, device):
        for m in self._modules:
            m.to(device)
        return self

    def train(self):
        for m in self._modules:
            m.train()

    def eval(self):
        for m in self._modules:
            m.eval()

    def _edge_agg(self, torch, x, edges, node_count):
        if not edges:
            return x
        src_idx = torch.tensor([e[0] for e in edges] + [e[1] for e in edges], dtype=torch.long, device=x.device)
        dst_idx = torch.tensor([e[1] for e in edges] + [e[0] for e in edges], dtype=torch.long, device=x.device)
        agg = torch.zeros(node_count, x.shape[1], dtype=x.dtype, device=x.device)
        agg.index_add_(0, dst_idx, x[src_idx])
        deg = torch.zeros(node_count, 1, dtype=x.dtype, device=x.device)
        one = torch.ones(dst_idx.shape[0], 1, dtype=x.dtype, device=x.device)
        deg.index_add_(0, dst_idx, one)
        deg = torch.clamp(deg, min=1.0)
        return agg / deg

    def _face_agg(self, torch, x, faces, node_count):
        if not faces:
            return torch.zeros(node_count, x.shape[1], dtype=x.dtype, device=x.device)
        f_idx = torch.tensor(faces, dtype=torch.long, device=x.device)
        face_feat = x[f_idx].mean(dim=1)
        out = torch.zeros(node_count, x.shape[1], dtype=x.dtype, device=x.device)
        deg = torch.zeros(node_count, 1, dtype=x.dtype, device=x.device)
        for j in range(3):
            idx = f_idx[:, j]
            out.index_add_(0, idx, face_feat)
            deg.index_add_(0, idx, torch.ones(idx.shape[0], 1, dtype=x.dtype, device=x.device))
        deg = torch.clamp(deg, min=1.0)
        return out / deg

    def forward_case(self, torch, case: dict, teacher_forcing: bool):
        node = torch.tensor(case["node_features"], dtype=torch.float32)
        target = torch.tensor(case["response_u"], dtype=torch.float32)
        gm = torch.tensor(case["ground_motion_g"], dtype=torch.float32)
        edges = [[int(u), int(v)] for u, v in case["edges"]]
        faces = [[int(i), int(j), int(k)] for i, j, k in case.get("faces", [])]

        node_count = int(node.shape[0])
        seq_len = int(target.shape[0])
        h = torch.zeros(node_count, self.in_proj.out_features, dtype=torch.float32, device=node.device)
        u_prev = torch.zeros(node_count, dtype=torch.float32, device=node.device)
        preds = []

        for t in range(seq_len):
            g_t = gm[t].reshape(1).repeat(node_count).unsqueeze(-1)
            x = torch.cat([node, u_prev.unsqueeze(-1), g_t], dim=1)
            x = torch.relu(self.in_proj(x))
            nei = self._edge_agg(torch, x, edges, node_count)
            face = self._face_agg(torch, x, faces, node_count)
            x = torch.relu(self.self_proj(x) + self.nei_proj(nei) + self.face_proj(face))
            h = self.gru(x, h)
            du = self.out_proj(h).squeeze(-1)
            u_next = u_prev + du
            preds.append(u_next)
            if teacher_forcing:
                u_prev = target[t]
            else:
                u_prev = u_next

        pred = torch.stack(preds, dim=0)
        return pred, target


def _split_cases(cases: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    train = [c for c in cases if c.get("split") == "train"]
    val = [c for c in cases if c.get("split") == "val"]
    test = [c for c in cases if c.get("split") == "test"]
    return train, val, test


def _evaluate(torch, model: SimplicialTemporalGNN, cases: list[dict], rollout: bool) -> dict:
    if not cases:
        return {"case_count": 0, "mae_pct": 0.0, "peak_error_pct": 0.0, "torsion_mae_pct": 0.0}
    model.eval()
    err = 0.0
    ref = 0.0
    torsion_err = 0.0
    torsion_ref = 0.0
    peaks = []
    with torch.no_grad():
        for case in cases:
            pred, target = model.forward_case(torch, case=case, teacher_forcing=not rollout)
            ae = torch.abs(pred - target)
            ar = torch.abs(target)
            err += float(ae.sum().item())
            ref += float(ar.sum().item())
            peaks.append(100.0 * float(torch.max(ae).item()) / max(1e-9, float(torch.max(ar).item())))
            if bool(case.get("torsion_sensitive", False)):
                torsion_err += float(ae.sum().item())
                torsion_ref += float(ar.sum().item())
    torsion_mae_pct = 0.0 if torsion_ref <= 1e-9 else 100.0 * torsion_err / torsion_ref
    return {
        "case_count": len(cases),
        "mae_pct": 100.0 * err / max(1e-9, ref),
        "peak_error_pct": sum(peaks) / max(1, len(peaks)),
        "torsion_mae_pct": torsion_mae_pct,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--baseline-report", default="implementation/phase1/spatiotemporal_data/tgnn_baseline_report.json")
    p.add_argument("--out", default="implementation/phase1/spatiotemporal_data/simplicial_tgnn_report.json")
    p.add_argument("--ckpt", default="implementation/phase1/spatiotemporal_data/simplicial_tgnn.pt")
    p.add_argument("--max-cases", type=int, default=900)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--hidden-dim", type=int, default=56)
    p.add_argument("--lr", type=float, default=9e-4)
    p.add_argument("--max-val-mae-pct", type=float, default=25.0)
    p.add_argument("--seed", type=int, default=23)
    args = p.parse_args()

    torch, F = _require_torch()
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))

    cases = load_jsonl(Path(args.dataset), max_cases=int(args.max_cases))
    if not cases:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-simplicial-tgnn",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_DATASET_EMPTY",
            "reason": REASONS["ERR_DATASET_EMPTY"],
        }
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    baseline = {}
    b_path = Path(args.baseline_report)
    if b_path.exists():
        baseline = json.loads(b_path.read_text(encoding="utf-8"))

    train_cases, val_cases, test_cases = _split_cases(cases)
    if not val_cases:
        val_cases = train_cases[: max(1, len(train_cases) // 5)]

    model = SimplicialTemporalGNN(torch, node_feat_dim=5, hidden_dim=int(args.hidden_dim)).to("cpu")
    optimizer = torch.optim.Adam(list(model.parameters()), lr=float(args.lr))

    history = []
    for ep in range(int(args.epochs)):
        model.train()
        random.shuffle(train_cases)
        total_loss = 0.0
        for case in train_cases:
            pred, target = model.forward_case(torch, case=case, teacher_forcing=True)
            loss = F.mse_loss(pred, target)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(model.parameters()), max_norm=1.0)
            optimizer.step()
            total_loss += float(loss.detach().item())
        val_eval = _evaluate(torch, model, val_cases, rollout=False)
        val_roll = _evaluate(torch, model, val_cases, rollout=True)
        history.append(
            {
                "epoch": ep + 1,
                "train_loss": total_loss / max(1, len(train_cases)),
                "val_mae_pct": val_eval["mae_pct"],
                "val_torsion_mae_pct": val_eval["torsion_mae_pct"],
                "val_rollout_mae_pct": val_roll["mae_pct"],
            }
        )

    val_metrics = _evaluate(torch, model, val_cases, rollout=False)
    val_rollout_metrics = _evaluate(torch, model, val_cases, rollout=True)
    test_metrics = _evaluate(torch, model, test_cases, rollout=False)
    test_rollout_metrics = _evaluate(torch, model, test_cases, rollout=True)
    baseline_torsion = float((baseline.get("validation_metrics") or {}).get("torsion_mae_pct", 0.0))
    torsion_improvement_pct = baseline_torsion - float(val_metrics["torsion_mae_pct"])

    contract_pass = bool(val_metrics["mae_pct"] <= float(args.max_val_mae_pct))
    reason_code = "PASS" if contract_pass else "ERR_METRIC_FAIL"

    ckpt_path = Path(args.ckpt)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "meta": {
                "hidden_dim": int(args.hidden_dim),
                "epochs": int(args.epochs),
                "lr": float(args.lr),
                "seed": int(args.seed),
            },
        },
        ckpt_path,
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-train-simplicial-tgnn",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "dataset": args.dataset,
            "baseline_report": args.baseline_report,
            "max_cases": int(args.max_cases),
            "epochs": int(args.epochs),
            "hidden_dim": int(args.hidden_dim),
            "lr": float(args.lr),
            "seed": int(args.seed),
        },
        "split_counts": {"train": len(train_cases), "val": len(val_cases), "test": len(test_cases)},
        "validation_metrics": val_metrics,
        "validation_rollout_metrics": val_rollout_metrics,
        "test_metrics": test_metrics,
        "test_rollout_metrics": test_rollout_metrics,
        "comparison_to_baseline": {
            "baseline_torsion_mae_pct": baseline_torsion,
            "simplicial_torsion_mae_pct": float(val_metrics["torsion_mae_pct"]),
            "torsion_improvement_pct_point": torsion_improvement_pct,
        },
        "history_tail": history[-5:],
        "checkpoint": str(ckpt_path),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote simplicial tgnn report: {out}")
    print(f"Saved checkpoint: {ckpt_path}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
