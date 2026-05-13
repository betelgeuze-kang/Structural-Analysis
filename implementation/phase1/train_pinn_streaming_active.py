#!/usr/bin/env python3
"""PINN + on-the-fly streaming + active learning trainer.

The trainer does not pre-materialize a huge dataset on disk.
Each batch is generated online from the physics simulator, consumed once,
and discarded. A hard-case pool is updated periodically by active sampling.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Iterable


def _require_torch():
    try:
        import torch  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"torch is required for PINN training: {exc}")
    return torch


from spatiotemporal_dataset_utils import (  # noqa: E402
    CaseConfig,
    MATERIALS,
    TOPOLOGIES,
    build_random_case,
)


G = 9.80665
EPS = 1e-9

REASONS = {
    "PASS": "streaming pinn training completed",
    "ERR_METRIC_FAIL": "validation metrics exceeded threshold",
}


def _one_hot(index: int, size: int) -> list[float]:
    out = [0.0 for _ in range(size)]
    out[index] = 1.0
    return out


def _global_response(case: dict) -> list[float]:
    rows = case["response_u"]
    return [sum(float(v) for v in row) / max(1, len(row)) for row in rows]


def _case_context(case: dict) -> list[float]:
    node = case["node_features"]
    n = max(1, len(node))
    m = sum(float(r[0]) for r in node) / n
    k = sum(float(r[1]) for r in node) / n
    c = sum(float(r[2]) for r in node) / n
    tors = sum(float(r[4]) for r in node) / n
    topo_i = TOPOLOGIES.index(str(case["topology_type"]))
    mat_i = MATERIALS.index(str(case["material_type"]))
    return [m, k, c, tors, float(case["node_count"])] + _one_hot(topo_i, len(TOPOLOGIES)) + _one_hot(mat_i, len(MATERIALS))


def _build_tensor_batch(torch, cases: list[dict]) -> tuple:
    b = len(cases)
    t_len = int(cases[0]["seq_len"])
    ctx_dim = 5 + len(TOPOLOGIES) + len(MATERIALS)
    x = torch.zeros(b, t_len, 2 + ctx_dim, dtype=torch.float32)
    y = torch.zeros(b, t_len, dtype=torch.float32)
    m = torch.zeros(b, 1, dtype=torch.float32)
    c = torch.zeros(b, 1, dtype=torch.float32)
    k = torch.zeros(b, 1, dtype=torch.float32)
    h_scale = torch.zeros(b, 1, dtype=torch.float32)

    for i, case in enumerate(cases):
        gm = [float(v) for v in case["ground_motion_g"]]
        resp = _global_response(case)
        ctx = _case_context(case)
        for t in range(t_len):
            x[i, t, 0] = gm[t]
            x[i, t, 1] = t / max(1, t_len - 1)
            for j, v in enumerate(ctx):
                x[i, t, 2 + j] = float(v)
            y[i, t] = float(resp[t])
        m[i, 0] = float(ctx[0])
        k[i, 0] = float(ctx[1])
        c[i, 0] = float(ctx[2])
        # Height-weighted forcing scale surrogate.
        h_scale[i, 0] = 1.05 + 0.15 * min(2.0, float(ctx[4]) / 50.0)

    return x, y, m, c, k, h_scale


class StreamingPINNModel:
    def __init__(self, torch, in_dim: int, hidden: int):
        nn = torch.nn
        self.fc_in = nn.Linear(in_dim, hidden)
        self.gru = nn.GRU(input_size=hidden, hidden_size=hidden, num_layers=1, batch_first=True)
        self.fc_mid = nn.Linear(hidden, hidden)
        self.fc_out = nn.Linear(hidden, 1)
        self._modules = [self.fc_in, self.gru, self.fc_mid, self.fc_out]

    def parameters(self) -> Iterable:
        for m in self._modules:
            for p in m.parameters():
                yield p

    def to(self, device: str):
        for m in self._modules:
            m.to(device)
        return self

    def train(self):
        for m in self._modules:
            m.train()

    def eval(self):
        for m in self._modules:
            m.eval()

    def state_dict(self) -> dict:
        return {
            "fc_in": self.fc_in.state_dict(),
            "gru": self.gru.state_dict(),
            "fc_mid": self.fc_mid.state_dict(),
            "fc_out": self.fc_out.state_dict(),
        }

    def forward(self, torch, x):
        h = torch.relu(self.fc_in(x))
        h, _ = self.gru(h)
        h = torch.relu(self.fc_mid(h))
        y = 0.25 * torch.tanh(self.fc_out(h).squeeze(-1))
        return y


@dataclass
class TrainConfig:
    seq_len: int
    dt: float
    coupling_k: float
    batch_size: int
    steps: int
    active_every: int
    active_candidates: int
    active_add: int
    hard_pool_cap: int
    val_cases: int
    seed: int


def _physics_residual_loss(torch, pred_u, gm, m, c, k, h_scale, dt: float):
    # pred_u: [B,T], gm: [B,T]
    v = (pred_u[:, 1:] - pred_u[:, :-1]) / dt
    a = (v[:, 1:] - v[:, :-1]) / dt
    u_mid = pred_u[:, 2:]
    v_mid = v[:, 1:]
    gm_mid = gm[:, 2:]

    ext = -m * (gm_mid * G) * h_scale
    r = m * a + c * v_mid + k * u_mid - ext
    gm_peak = torch.max(torch.abs(gm), dim=1, keepdim=True).values
    force_scale = m * G * (gm_peak + 0.05) * h_scale + 0.05 * k + 0.05 * c / max(dt, 1e-6)
    r_norm = r / torch.clamp(force_scale, min=1.0)
    return torch.mean(r_norm * r_norm)


def _batch_metrics(torch, pred_u, target_u):
    abs_err = torch.abs(pred_u - target_u)
    abs_ref = torch.abs(target_u)
    denom = float(abs_ref.sum().item()) + 0.02 * float(target_u.numel())
    mae_pct = 100.0 * float(abs_err.sum().item()) / max(EPS, denom)
    peak_pct = 100.0 * float(torch.max(abs_err).item()) / max(EPS, float(torch.max(abs_ref).item()))
    return mae_pct, peak_pct


def _sample_case(cfg: TrainConfig, rng: random.Random, idx: int, hard_bias: float = 0.0) -> dict:
    ccfg = CaseConfig(seq_len=int(cfg.seq_len), dt=float(cfg.dt), coupling_k=float(cfg.coupling_k))
    return build_random_case(case_id=f"S-{idx:09d}", cfg=ccfg, rng=rng, hard_bias=hard_bias)


def _sample_batch(cfg: TrainConfig, rng: random.Random, hard_pool: deque, idx_start: int) -> list[dict]:
    out: list[dict] = []
    hard_take = min(len(hard_pool), max(0, int(cfg.batch_size * 0.35)))
    for _ in range(hard_take):
        out.append(random.choice(list(hard_pool)))
    while len(out) < int(cfg.batch_size):
        out.append(_sample_case(cfg, rng, idx=idx_start + len(out)))
    return out


def _active_refresh(
    torch,
    model: StreamingPINNModel,
    cfg: TrainConfig,
    rng: random.Random,
    hard_pool: deque,
    case_counter_start: int,
) -> tuple[int, float]:
    candidates = [_sample_case(cfg, rng, idx=case_counter_start + i, hard_bias=0.45) for i in range(int(cfg.active_candidates))]
    scored = []
    model.eval()
    with torch.no_grad():
        for c in candidates:
            x, y, m, cv, k, hs = _build_tensor_batch(torch, [c])
            pred = model.forward(torch, x)
            data_mae, _ = _batch_metrics(torch, pred, y)
            phys = float(_physics_residual_loss(torch, pred, x[:, :, 0], m, cv, k, hs, dt=float(cfg.dt)).item())
            score = 0.65 * phys + 0.35 * (data_mae / 100.0)
            scored.append((score, c))
    scored.sort(key=lambda z: z[0], reverse=True)
    chosen = scored[: int(cfg.active_add)]
    for _, c in chosen:
        hard_pool.append(c)
    avg_score = 0.0 if not chosen else sum(s for s, _ in chosen) / len(chosen)
    return len(chosen), avg_score


def _evaluate_streaming(torch, model: StreamingPINNModel, cfg: TrainConfig, rng_seed: int) -> dict:
    rng = random.Random(int(rng_seed))
    cases = [_sample_case(cfg, rng, idx=700_000 + i, hard_bias=0.22) for i in range(int(cfg.val_cases))]
    mae_vals = []
    peak_vals = []
    phys_vals = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(cases), int(cfg.batch_size)):
            batch = cases[i : i + int(cfg.batch_size)]
            x, y, m, cv, k, hs = _build_tensor_batch(torch, batch)
            pred = model.forward(torch, x)
            mae_pct, peak_pct = _batch_metrics(torch, pred, y)
            phys = float(_physics_residual_loss(torch, pred, x[:, :, 0], m, cv, k, hs, dt=float(cfg.dt)).item())
            mae_vals.append(mae_pct)
            peak_vals.append(peak_pct)
            phys_vals.append(phys)
    return {
        "case_count": len(cases),
        "mae_pct": sum(mae_vals) / max(1, len(mae_vals)),
        "peak_error_pct": sum(peak_vals) / max(1, len(peak_vals)),
        "physics_residual_mse": sum(phys_vals) / max(1, len(phys_vals)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/spatiotemporal_data/pinn_streaming_active_report.json")
    p.add_argument("--ckpt", default="implementation/phase1/spatiotemporal_data/pinn_streaming_active.pt")
    p.add_argument("--steps", type=int, default=260)
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--seq-len", type=int, default=120)
    p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--coupling-k", type=float, default=2800.0)
    p.add_argument("--hidden", type=int, default=80)
    p.add_argument("--lr", type=float, default=1.5e-3)
    p.add_argument("--lambda-phys", type=float, default=3.2)
    p.add_argument("--lambda-smooth", type=float, default=0.04)
    p.add_argument("--active-every", type=int, default=40)
    p.add_argument("--active-candidates", type=int, default=80)
    p.add_argument("--active-add", type=int, default=16)
    p.add_argument("--hard-pool-cap", type=int, default=240)
    p.add_argument("--val-cases", type=int, default=80)
    p.add_argument("--max-val-mae-pct", type=float, default=85.0)
    p.add_argument("--max-val-physics-mse", type=float, default=3.0)
    p.add_argument("--seed", type=int, default=23)
    args = p.parse_args()

    torch = _require_torch()
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))

    cfg = TrainConfig(
        seq_len=int(args.seq_len),
        dt=float(args.dt),
        coupling_k=float(args.coupling_k),
        batch_size=int(args.batch_size),
        steps=int(args.steps),
        active_every=int(args.active_every),
        active_candidates=int(args.active_candidates),
        active_add=int(args.active_add),
        hard_pool_cap=int(args.hard_pool_cap),
        val_cases=int(args.val_cases),
        seed=int(args.seed),
    )
    rng = random.Random(int(args.seed))
    hard_pool: deque = deque(maxlen=int(cfg.hard_pool_cap))

    in_dim = 2 + 5 + len(TOPOLOGIES) + len(MATERIALS)
    model = StreamingPINNModel(torch, in_dim=in_dim, hidden=int(args.hidden)).to("cpu")
    optimizer = torch.optim.Adam(list(model.parameters()), lr=float(args.lr))

    history = []
    streamed_cases = 0
    active_events = 0
    hard_added_total = 0
    active_score_sum = 0.0
    case_counter = 0

    for step in range(1, int(cfg.steps) + 1):
        model.train()
        batch = _sample_batch(cfg, rng, hard_pool, idx_start=case_counter)
        case_counter += len(batch)
        streamed_cases += len(batch)

        x, y, m, cv, k, hs = _build_tensor_batch(torch, batch)
        pred = model.forward(torch, x)
        data_loss = torch.mean((pred - y) ** 2)
        phys_loss = _physics_residual_loss(torch, pred, x[:, :, 0], m, cv, k, hs, dt=float(cfg.dt))
        smooth_loss = torch.mean((pred[:, 1:] - pred[:, :-1]) ** 2)
        total_loss = data_loss + float(args.lambda_phys) * phys_loss + float(args.lambda_smooth) * smooth_loss

        optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(list(model.parameters()), max_norm=1.2)
        optimizer.step()

        train_mae_pct, train_peak_pct = _batch_metrics(torch, pred.detach(), y)
        history.append(
            {
                "step": step,
                "loss_total": float(total_loss.detach().item()),
                "loss_data": float(data_loss.detach().item()),
                "loss_physics": float(phys_loss.detach().item()),
                "loss_smooth": float(smooth_loss.detach().item()),
                "train_mae_pct": train_mae_pct,
                "train_peak_error_pct": train_peak_pct,
                "hard_pool_size": len(hard_pool),
            }
        )

        if int(cfg.active_every) > 0 and step % int(cfg.active_every) == 0:
            added, avg_score = _active_refresh(
                torch=torch,
                model=model,
                cfg=cfg,
                rng=rng,
                hard_pool=hard_pool,
                case_counter_start=case_counter,
            )
            case_counter += int(cfg.active_candidates)
            hard_added_total += added
            active_events += 1
            active_score_sum += avg_score

    val_metrics = _evaluate_streaming(torch, model, cfg=cfg, rng_seed=int(args.seed) + 101)
    test_metrics = _evaluate_streaming(torch, model, cfg=cfg, rng_seed=int(args.seed) + 151)
    avg_active_score = 0.0 if active_events == 0 else active_score_sum / active_events

    contract_pass = bool(
        val_metrics["mae_pct"] <= float(args.max_val_mae_pct)
        and val_metrics["physics_residual_mse"] <= float(args.max_val_physics_mse)
    )
    reason_code = "PASS" if contract_pass else "ERR_METRIC_FAIL"

    ckpt_path = Path(args.ckpt)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "meta": {
                "in_dim": in_dim,
                "hidden": int(args.hidden),
                "steps": int(args.steps),
                "seed": int(args.seed),
            },
        },
        ckpt_path,
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-pinn-streaming-active",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "steps": int(args.steps),
            "batch_size": int(args.batch_size),
            "seq_len": int(args.seq_len),
            "dt": float(args.dt),
            "coupling_k": float(args.coupling_k),
            "hidden": int(args.hidden),
            "lr": float(args.lr),
            "lambda_phys": float(args.lambda_phys),
            "lambda_smooth": float(args.lambda_smooth),
            "active_every": int(args.active_every),
            "active_candidates": int(args.active_candidates),
            "active_add": int(args.active_add),
            "hard_pool_cap": int(args.hard_pool_cap),
            "val_cases": int(args.val_cases),
            "seed": int(args.seed),
        },
        "streaming_summary": {
            "streamed_case_count": int(streamed_cases),
            "active_events": int(active_events),
            "hard_cases_added_total": int(hard_added_total),
            "hard_pool_final_size": int(len(hard_pool)),
            "average_active_score": float(avg_active_score),
            "estimated_equivalent_saved_cases": int(streamed_cases + active_events * int(args.active_candidates)),
        },
        "pinn_principle": {
            "hard_constraint_in_loss": True,
            "equation": "M*u_ddot + C*u_dot + K*u - f_ext = 0",
            "physics_loss_included": True,
            "on_the_fly_generation": True,
            "active_learning_enabled": True,
        },
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "history_tail": history[-12:],
        "checkpoint": str(ckpt_path),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote streaming PINN report: {out}")
    print(f"Saved checkpoint: {ckpt_path}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
