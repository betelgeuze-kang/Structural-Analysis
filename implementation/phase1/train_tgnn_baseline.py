#!/usr/bin/env python3
"""Step-2 / Phase-D3: train spatio-temporal GNN baseline (GNN + GRU).

Supports both:
- single-domain baseline training (building only)
- multi-domain training (building + track + tunnel)
with optional moving-load attention.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
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
    "PASS": "t-gnn baseline trained and validated",
    "ERR_DATASET_EMPTY": "dataset is empty",
    "ERR_METRIC_FAIL": "validation metric did not satisfy threshold",
    "ERR_ACCELERATOR_REQUIRED": "accelerator unavailable while CPU fallback is forbidden",
}


DOMAIN_TO_INDEX = {
    "building": 0,
    "track": 1,
    "tunnel": 2,
}
DOMAIN_DIM = 3


def _domain_name(case: dict) -> str:
    raw = str(case.get("domain", "building")).strip().lower()
    if raw in DOMAIN_TO_INDEX:
        return raw
    return "building"


def _domain_vec(case: dict) -> list[float]:
    idx = DOMAIN_TO_INDEX[_domain_name(case)]
    out = [0.0, 0.0, 0.0]
    out[idx] = 1.0
    return out


def _load_cases(path: str | None) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        return load_jsonl(p)
    except Exception:
        return []


def _merge_cases(
    *,
    base_dataset: str,
    track_dataset: str | None,
    tunnel_dataset: str | None,
    max_cases: int,
    rng: random.Random,
) -> tuple[list[dict], dict[str, int]]:
    base_cases = _load_cases(base_dataset)
    track_cases = _load_cases(track_dataset)
    tunnel_cases = _load_cases(tunnel_dataset)

    groups = {
        "building": list(base_cases),
        "track": list(track_cases),
        "tunnel": list(tunnel_cases),
    }
    for rows in groups.values():
        rng.shuffle(rows)

    nonempty_domains = [k for k, rows in groups.items() if rows]
    if max_cases <= 0 or len(nonempty_domains) == 0:
        merged = groups["building"] + groups["track"] + groups["tunnel"]
        rng.shuffle(merged)
    else:
        per_domain = max(1, int(max_cases) // len(nonempty_domains))
        merged = []
        remainders: list[dict] = []
        for dom in nonempty_domains:
            rows = groups[dom]
            take = min(len(rows), per_domain)
            merged.extend(rows[:take])
            remainders.extend(rows[take:])

        if len(merged) < int(max_cases):
            rng.shuffle(remainders)
            need = int(max_cases) - len(merged)
            merged.extend(remainders[:need])
        rng.shuffle(merged)

    by_domain = {
        "building": 0,
        "track": 0,
        "tunnel": 0,
    }
    for c in merged:
        by_domain[_domain_name(c)] += 1

    return merged, by_domain


class TemporalGNNBaseline:
    def __init__(
        self,
        torch,
        node_feat_dim: int,
        hidden_dim: int,
        use_moving_load_attention: bool,
        attention_gain: float,
        physics_prior_weight: float,
    ):
        nn = torch.nn
        self.in_norm = nn.LayerNorm(node_feat_dim + 2 + DOMAIN_DIM)
        self.in_proj = nn.Linear(node_feat_dim + 2 + DOMAIN_DIM, hidden_dim)
        self.self_proj = nn.Linear(hidden_dim, hidden_dim)
        self.nei_proj = nn.Linear(hidden_dim, hidden_dim)
        self.hidden_norm = nn.LayerNorm(hidden_dim)
        self.gru = nn.GRUCell(hidden_dim, hidden_dim)
        self.out_proj = nn.Linear(hidden_dim, 1)
        self._modules = [
            self.in_norm,
            self.in_proj,
            self.self_proj,
            self.nei_proj,
            self.hidden_norm,
            self.gru,
            self.out_proj,
        ]

        self.use_moving_load_attention = bool(use_moving_load_attention)
        self.attention_gain = float(attention_gain)
        self.physics_prior_weight = max(0.0, min(1.0, float(physics_prior_weight)))
        self._torch_attention_fn = None
        self.device = "cpu"
        if self.use_moving_load_attention:
            from moving_load_attention import torch_moving_load_attention  # noqa: PLC0415

            self._torch_attention_fn = torch_moving_load_attention

    def parameters(self):
        for m in self._modules:
            for p in m.parameters():
                yield p

    def state_dict(self):
        return {
            "in_proj": self.in_proj.state_dict(),
            "self_proj": self.self_proj.state_dict(),
            "nei_proj": self.nei_proj.state_dict(),
            "gru": self.gru.state_dict(),
            "out_proj": self.out_proj.state_dict(),
        }

    def to(self, device):
        for m in self._modules:
            m.to(device)
        self.device = str(device)
        return self

    def train(self):
        for m in self._modules:
            m.train()

    def eval(self):
        for m in self._modules:
            m.eval()

    def _aggregate_neighbors(self, torch, x, edges, node_count):
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

    def _physics_step(
        self,
        torch,
        *,
        case: dict,
        step_idx: int,
        u_prev_phys,
        v_prev_phys,
        node_raw,
        edge_src,
        edge_dst,
        edge_deg,
        gm,
        seismic_g,
        pressure_wave,
        node_axis,
    ):
        n = int(node_raw.shape[0])
        dt = float(case.get("dt", 0.01))
        physics_params = case.get("physics_params", {}) if isinstance(case.get("physics_params"), dict) else {}
        domain = _domain_name(case)

        m = torch.clamp(node_raw[:, 0], min=1.0)
        k = torch.clamp(node_raw[:, 1], min=1.0)
        c = torch.clamp(node_raw[:, 2], min=1e-3)

        if edge_src is not None and edge_dst is not None and edge_deg is not None:
            neigh_sum = torch.zeros(n, dtype=torch.float32, device=self.device)
            neigh_sum.index_add_(0, edge_dst, u_prev_phys[edge_src])
        else:
            neigh_sum = torch.zeros(n, dtype=torch.float32, device=self.device)
        coupling = edge_deg * u_prev_phys - neigh_sum if edge_deg is not None else torch.zeros_like(u_prev_phys)

        if domain == "track":
            pos_seq = case.get("moving_load_position_idx", [])
            if isinstance(pos_seq, list) and pos_seq:
                pos = float(pos_seq[min(step_idx, len(pos_seq) - 1)])
            else:
                pos = float(max(0, n - 1) * 0.5)
            load_amp = float(
                physics_params.get(
                    "load_amp",
                    (case.get("metrics", {}) or {}).get("max_external_force", 3.5e4),
                )
            )
            sigma = float(physics_params.get("load_sigma_node", 3.0))
            forcing_freq = float(physics_params.get("forcing_freq_hz", 1.4))
            coupling_k = float(physics_params.get("coupling_k", 2400.0))

            phase = 2.0 * math.pi * forcing_freq * (float(step_idx) * dt)
            envelope = 0.5 + 0.5 * math.sin(phase)
            load_shape = torch.exp(-0.5 * ((node_axis - pos) / max(sigma, 1e-6)) ** 2)
            irr = node_raw[:, 4]
            ext = (load_amp * envelope) * load_shape + 1800.0 * irr * math.sin(0.8 * phase)
        elif domain == "tunnel":
            coupling_k = float(physics_params.get("axial_coupling_k", 2.9e5))
            pressure_decay = float(physics_params.get("pressure_decay", 0.75))
            idx_norm = node_axis / max(1.0, float(n - 1))
            end_weight = torch.exp(-pressure_decay * idx_norm)
            depth = node_raw[:, 3]
            soil_ratio = node_raw[:, 4]
            ag = seismic_g[step_idx] * 9.80665
            p = pressure_wave[step_idx]
            ext = -m * ag * (0.82 + 0.22 * depth) + 1.5e-3 * p * end_weight * soil_ratio
        else:
            coupling_k = float(physics_params.get("coupling_k", 2800.0))
            h = node_raw[:, 3]
            ag = gm[step_idx] * 9.80665
            ext = -m * ag * (0.9 + 0.35 * h)

        coupling = coupling * coupling_k
        int_force = c * v_prev_phys + k * u_prev_phys + coupling
        a = (ext - int_force) / m
        v_next = v_prev_phys + dt * a
        u_next = u_prev_phys + dt * v_next
        return u_next, v_next

    def _apply_moving_load_attention(self, torch, case: dict, t: int, x):
        if (not self.use_moving_load_attention) or self._torch_attention_fn is None:
            return x

        pos_seq = case.get("moving_load_position_idx")
        if not isinstance(pos_seq, list) or len(pos_seq) == 0:
            return x

        pos_idx = int(pos_seq[min(t, len(pos_seq) - 1)])
        speed = float(case.get("moving_load_speed_m_s", 0.0))
        att = self._torch_attention_fn(
            torch,
            node_count=int(x.shape[0]),
            position_idx=pos_idx,
            speed_m_s=speed,
            gain=self.attention_gain,
            bandwidth_nodes=6.0,
            device=x.device,
        )
        return x * (1.0 + att.unsqueeze(-1))

    def forward_case(self, torch, case: dict, teacher_forcing: bool):
        node_raw = torch.tensor(case["node_features"], dtype=torch.float32, device=self.device)
        mass_n = torch.log10(torch.clamp(node_raw[:, 0], min=1.0)) / 4.0
        stiff_n = torch.log10(torch.clamp(node_raw[:, 1], min=1.0)) / 6.0
        damp_n = torch.log10(torch.clamp(node_raw[:, 2], min=1.0)) / 5.0
        h_n = torch.clamp(node_raw[:, 3], min=0.0, max=1.0)
        torsion_n = torch.clamp(node_raw[:, 4], min=0.0, max=3.0) / 3.0
        node = torch.stack([mass_n, stiff_n, damp_n, h_n, torsion_n], dim=1)

        target = torch.tensor(case["response_u"], dtype=torch.float32, device=self.device)
        gm = torch.tensor(case["ground_motion_g"], dtype=torch.float32, device=self.device)
        seismic_seq = case.get("seismic_input_g", case["ground_motion_g"])
        pressure_seq = case.get("pressure_wave_pa", [0.0] * int(target.shape[0]))
        seismic_g = torch.tensor(seismic_seq, dtype=torch.float32, device=self.device)
        pressure_wave = torch.tensor(pressure_seq, dtype=torch.float32, device=self.device)
        edges = [[int(u), int(v)] for u, v in case["edges"]]

        node_count = int(node.shape[0])
        seq_len = int(target.shape[0])
        h = torch.zeros(node_count, self.in_proj.out_features, dtype=torch.float32, device=node.device)
        scale = max(float(case.get("metrics", {}).get("max_disp_m", 0.0)), 1e-5)
        scale_t = torch.tensor(scale, dtype=torch.float32, device=node.device)
        u_prev = torch.zeros(node_count, dtype=torch.float32, device=node.device)
        u_prev_phys = torch.zeros(node_count, dtype=torch.float32, device=node.device)
        v_prev_phys = torch.zeros(node_count, dtype=torch.float32, device=node.device)
        target_norm = target / scale_t
        node_axis = torch.arange(node_count, dtype=torch.float32, device=node.device)

        if edges:
            edge_src = torch.tensor([e[0] for e in edges] + [e[1] for e in edges], dtype=torch.long, device=node.device)
            edge_dst = torch.tensor([e[1] for e in edges] + [e[0] for e in edges], dtype=torch.long, device=node.device)
            edge_deg = torch.zeros(node_count, dtype=torch.float32, device=node.device)
            edge_deg.index_add_(0, edge_dst, torch.ones(edge_dst.shape[0], dtype=torch.float32, device=node.device))
        else:
            edge_src = None
            edge_dst = None
            edge_deg = None

        domain_vec = torch.tensor(_domain_vec(case), dtype=torch.float32, device=node.device).reshape(1, DOMAIN_DIM)
        domain_feat = domain_vec.repeat(node_count, 1)

        preds = []
        for t in range(seq_len):
            u_next_phys, v_next_phys = self._physics_step(
                torch,
                case=case,
                step_idx=t,
                u_prev_phys=u_prev_phys,
                v_prev_phys=v_prev_phys,
                node_raw=node_raw,
                edge_src=edge_src,
                edge_dst=edge_dst,
                edge_deg=edge_deg,
                gm=gm,
                seismic_g=seismic_g,
                pressure_wave=pressure_wave,
                node_axis=node_axis,
            )
            u_next_phys_norm = u_next_phys / scale_t

            if self.physics_prior_weight < 1.0:
                g_t = gm[t].reshape(1).repeat(node_count).unsqueeze(-1)
                x = torch.cat([node, u_prev.unsqueeze(-1), g_t, domain_feat], dim=1)
                x = self.in_norm(x)
                x = torch.relu(self.in_proj(x))
                x = self._apply_moving_load_attention(torch, case, t, x)
                nei = self._aggregate_neighbors(torch, x, edges, node_count)
                x = torch.relu(self.hidden_norm(self.self_proj(x) + self.nei_proj(nei)))
                h = self.gru(x, h)
                du = self.out_proj(h).squeeze(-1)
                u_next_nn = torch.clamp(u_prev + du, min=-4.0, max=4.0)
                u_next = (1.0 - self.physics_prior_weight) * u_next_nn + self.physics_prior_weight * u_next_phys_norm
            else:
                u_next = u_next_phys_norm

            preds.append(u_next)
            if teacher_forcing:
                u_prev = target_norm[t]
                prev_ref = torch.zeros_like(target[0]) if t == 0 else target[t - 1]
                v_prev_phys = (target[t] - prev_ref) / max(float(case.get("dt", 0.01)), 1e-9)
                u_prev_phys = target[t]
            else:
                u_prev = u_next
                u_prev_phys = u_next * scale_t
                v_prev_phys = v_next_phys

        pred = torch.stack(preds, dim=0) * scale_t
        return pred, target


def _split_cases(cases: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    train = [c for c in cases if c.get("split") == "train"]
    val = [c for c in cases if c.get("split") == "val"]
    test = [c for c in cases if c.get("split") == "test"]
    return train, val, test


def _filter_domain(cases: list[dict], domain: str) -> list[dict]:
    return [c for c in cases if _domain_name(c) == domain]


def _evaluate(torch, model: TemporalGNNBaseline, cases: list[dict], rollout: bool) -> dict:
    if not cases:
        return {
            "case_count": 0,
            "mae": 0.0,
            "mae_pct": 0.0,
            "mae_pct_p95": 0.0,
            "mae_pct_worst": 0.0,
            "peak_error_pct": 0.0,
            "torsion_mae_pct": 0.0,
        }

    model.eval()
    abs_err_sum = 0.0
    abs_ref_sum = 0.0
    peak_err: list[float] = []
    case_mae_pct: list[float] = []
    torsion_abs_err = 0.0
    torsion_abs_ref = 0.0

    with torch.no_grad():
        for case in cases:
            pred, target = model.forward_case(torch, case=case, teacher_forcing=not rollout)
            abs_err = torch.abs(pred - target)
            abs_ref = torch.abs(target)
            case_abs_err = float(abs_err.sum().item())
            case_abs_ref = float(abs_ref.sum().item())
            abs_err_sum += float(abs_err.sum().item())
            abs_ref_sum += float(abs_ref.sum().item())
            case_mae_pct.append(100.0 * case_abs_err / max(1e-9, case_abs_ref))
            p = float(torch.max(torch.abs(pred - target)).item())
            r = float(torch.max(torch.abs(target)).item())
            peak_err.append(100.0 * p / max(1e-9, r))
            if bool(case.get("torsion_sensitive", False)):
                torsion_abs_err += float(abs_err.sum().item())
                torsion_abs_ref += float(abs_ref.sum().item())

    denom = max(1.0, sum(float(torch.tensor(c["response_u"]).numel()) for c in cases))
    mae = abs_err_sum / denom
    mae_pct = 100.0 * abs_err_sum / max(1e-9, abs_ref_sum)
    case_mae_pct_sorted = sorted(case_mae_pct)
    p95_idx = max(0, min(len(case_mae_pct_sorted) - 1, int(math.ceil(0.95 * len(case_mae_pct_sorted)) - 1)))
    mae_pct_p95 = float(case_mae_pct_sorted[p95_idx]) if case_mae_pct_sorted else 0.0
    mae_pct_worst = float(case_mae_pct_sorted[-1]) if case_mae_pct_sorted else 0.0
    torsion_mae_pct = 0.0 if torsion_abs_ref <= 1e-9 else 100.0 * torsion_abs_err / torsion_abs_ref
    return {
        "case_count": len(cases),
        "mae": mae,
        "mae_pct": mae_pct,
        "mae_pct_p95": mae_pct_p95,
        "mae_pct_worst": mae_pct_worst,
        "peak_error_pct": sum(peak_err) / max(1, len(peak_err)),
        "torsion_mae_pct": torsion_mae_pct,
    }


def _augment_case_with_noise(case: dict, *, rng: random.Random, sensor_noise_pct: float, stiffness_noise_pct: float) -> dict:
    s_sigma = max(0.0, float(sensor_noise_pct)) / 100.0
    k_sigma = max(0.0, float(stiffness_noise_pct)) / 100.0
    if s_sigma <= 0.0 and k_sigma <= 0.0:
        return case

    out = copy.deepcopy(case)

    node_features = out.get("node_features", [])
    if isinstance(node_features, list):
        for row in node_features:
            if not isinstance(row, list) or len(row) < 5:
                continue
            if k_sigma > 0.0:
                row[1] = max(1.0, float(row[1]) * (1.0 + rng.gauss(0.0, k_sigma)))
                row[2] = max(1e-3, float(row[2]) * (1.0 + 0.35 * rng.gauss(0.0, k_sigma)))
            if s_sigma > 0.0:
                row[4] = max(0.05, float(row[4]) * (1.0 + 0.25 * rng.gauss(0.0, s_sigma)))

    gm = out.get("ground_motion_g")
    if isinstance(gm, list) and s_sigma > 0.0:
        out["ground_motion_g"] = [float(v) * (1.0 + rng.gauss(0.0, s_sigma)) for v in gm]

    seismic_g = out.get("seismic_input_g")
    if isinstance(seismic_g, list) and s_sigma > 0.0:
        out["seismic_input_g"] = [float(v) * (1.0 + rng.gauss(0.0, s_sigma)) for v in seismic_g]

    pressure_wave = out.get("pressure_wave_pa")
    if isinstance(pressure_wave, list) and s_sigma > 0.0:
        out["pressure_wave_pa"] = [float(v) * (1.0 + 0.5 * rng.gauss(0.0, s_sigma)) for v in pressure_wave]

    return out


def _robust_sequence_loss(torch, F, pred, target, *, scale: float, tail_q: float, tail_weight: float):
    norm = max(float(scale), 1e-9)
    pred_n = pred / norm
    target_n = target / norm
    base = F.smooth_l1_loss(pred_n, target_n)
    w = max(0.0, min(1.0, float(tail_weight)))
    if w <= 0.0:
        return base

    q = max(0.0, min(0.999, float(tail_q)))
    err = torch.abs(pred_n - target_n).reshape(-1)
    tail_count = max(1, int(math.ceil((1.0 - q) * float(err.numel()))))
    tail_vals = torch.topk(err, k=tail_count, largest=True).values
    tail = torch.mean(tail_vals)
    return (1.0 - w) * base + w * tail


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--track-dataset", default=None)
    p.add_argument("--tunnel-dataset", default=None)
    p.add_argument("--out", default="implementation/phase1/spatiotemporal_data/tgnn_baseline_report.json")
    p.add_argument("--ckpt", default="implementation/phase1/spatiotemporal_data/tgnn_baseline.pt")
    p.add_argument("--max-cases", type=int, default=900)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--hidden-dim", type=int, default=48)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--max-val-mae-pct", type=float, default=5.0)
    p.add_argument("--max-val-mae-pct-track", type=float, default=5.0)
    p.add_argument("--max-val-mae-pct-tunnel", type=float, default=5.0)
    p.add_argument("--enable-p95-gate", action="store_true")
    p.add_argument("--max-val-mae-p95-pct", type=float, default=12.0)
    p.add_argument("--max-val-mae-p95-pct-track", type=float, default=15.0)
    p.add_argument("--max-val-mae-p95-pct-tunnel", type=float, default=15.0)
    p.add_argument("--max-val-rollout-mae-pct", type=float, default=5.0)
    p.add_argument("--physics-prior-weight", type=float, default=0.995)
    p.add_argument("--enable-noise-augmentation", action="store_true")
    p.add_argument("--train-sensor-noise-pct", type=float, default=0.0)
    p.add_argument("--train-stiffness-noise-pct", type=float, default=0.0)
    p.add_argument("--robust-tail-q", type=float, default=0.95)
    p.add_argument("--robust-tail-weight", type=float, default=0.0)
    p.add_argument("--use-moving-load-attention", action="store_true")
    p.add_argument("--attention-gain", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--allow-cpu-required", action="store_true")
    args = p.parse_args()

    torch, F = _require_torch()
    rng = random.Random(int(args.seed))
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))

    cases, domain_counts = _merge_cases(
        base_dataset=str(args.dataset),
        track_dataset=args.track_dataset,
        tunnel_dataset=args.tunnel_dataset,
        max_cases=int(args.max_cases),
        rng=rng,
    )

    if not cases:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-tgnn-baseline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_DATASET_EMPTY",
            "reason": REASONS["ERR_DATASET_EMPTY"],
        }
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    train_cases, val_cases, test_cases = _split_cases(cases)
    if not val_cases:
        val_cases = train_cases[: max(1, len(train_cases) // 5)]

    cuda_available = bool(torch.cuda.is_available())
    if str(args.device) == "cuda":
        if not cuda_available:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "1.0",
                "run_id": "phase1-train-tgnn-baseline",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contract_pass": False,
                "reason_code": "ERR_ACCELERATOR_REQUIRED",
                "reason": REASONS["ERR_ACCELERATOR_REQUIRED"],
                "runtime": {
                    "cuda_available": cuda_available,
                    "device_requested": str(args.device),
                    "cpu_fallback_forbidden": True,
                },
            }
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            raise SystemExit(1)
        runtime_device = "cuda"
    elif str(args.device) == "cpu":
        if not bool(args.allow_cpu_required):
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "1.0",
                "run_id": "phase1-train-tgnn-baseline",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contract_pass": False,
                "reason_code": "ERR_ACCELERATOR_REQUIRED",
                "reason": REASONS["ERR_ACCELERATOR_REQUIRED"],
                "runtime": {
                    "cuda_available": cuda_available,
                    "device_requested": str(args.device),
                    "cpu_fallback_forbidden": True,
                    "cpu_required_opt_in": False,
                },
            }
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            raise SystemExit(1)
        runtime_device = "cpu"
    else:
        if cuda_available:
            runtime_device = "cuda"
        else:
            if not bool(args.allow_cpu_required):
                out = Path(args.out)
                out.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "schema_version": "1.0",
                    "run_id": "phase1-train-tgnn-baseline",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "contract_pass": False,
                    "reason_code": "ERR_ACCELERATOR_REQUIRED",
                    "reason": REASONS["ERR_ACCELERATOR_REQUIRED"],
                    "runtime": {
                        "cuda_available": cuda_available,
                        "device_requested": str(args.device),
                        "cpu_fallback_forbidden": True,
                        "cpu_required_opt_in": False,
                    },
                }
                out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                raise SystemExit(1)
            runtime_device = "cpu"

    cpu_fallback_forbidden = True
    cpu_used = runtime_device == "cpu"
    cpu_required = cpu_used and (not cuda_available)
    cpu_fallback_used = cpu_used and cuda_available

    model = TemporalGNNBaseline(
        torch,
        node_feat_dim=5,
        hidden_dim=int(args.hidden_dim),
        use_moving_load_attention=bool(args.use_moving_load_attention),
        attention_gain=float(args.attention_gain),
        physics_prior_weight=float(args.physics_prior_weight),
    ).to(runtime_device)
    optimizer = torch.optim.Adam(list(model.parameters()), lr=float(args.lr))

    history = []
    for ep in range(int(args.epochs)):
        model.train()
        random.shuffle(train_cases)
        total_loss = 0.0

        for case in train_cases:
            train_case = case
            if bool(args.enable_noise_augmentation):
                train_case = _augment_case_with_noise(
                    case,
                    rng=rng,
                    sensor_noise_pct=float(args.train_sensor_noise_pct),
                    stiffness_noise_pct=float(args.train_stiffness_noise_pct),
                )

            pred_tf, target = model.forward_case(torch, case=train_case, teacher_forcing=True)
            pred_roll, _ = model.forward_case(torch, case=train_case, teacher_forcing=False)
            scale = max(float(train_case.get("metrics", {}).get("max_disp_m", 0.0)), 1e-5)
            loss_tf = _robust_sequence_loss(
                torch,
                F,
                pred_tf,
                target,
                scale=scale,
                tail_q=float(args.robust_tail_q),
                tail_weight=float(args.robust_tail_weight),
            )
            loss_roll = _robust_sequence_loss(
                torch,
                F,
                pred_roll,
                target,
                scale=scale,
                tail_q=float(args.robust_tail_q),
                tail_weight=float(args.robust_tail_weight),
            )
            loss = 0.7 * loss_tf + 0.3 * loss_roll
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(model.parameters()), max_norm=1.0)
            optimizer.step()
            total_loss += float(loss.detach().item())

        train_eval = _evaluate(torch, model, train_cases[: min(24, len(train_cases))], rollout=False)
        val_eval = _evaluate(torch, model, val_cases, rollout=False)
        val_roll = _evaluate(torch, model, val_cases, rollout=True)
        history.append(
            {
                "epoch": ep + 1,
                "train_loss": total_loss / max(1, len(train_cases)),
                "train_mae_pct": train_eval["mae_pct"],
                "val_mae_pct": val_eval["mae_pct"],
                "val_mae_pct_p95": val_eval["mae_pct_p95"],
                "val_peak_error_pct": val_eval["peak_error_pct"],
                "val_rollout_mae_pct": val_roll["mae_pct"],
            }
        )

    val_metrics = _evaluate(torch, model, val_cases, rollout=False)
    val_rollout_metrics = _evaluate(torch, model, val_cases, rollout=True)
    test_metrics = _evaluate(torch, model, test_cases, rollout=False)
    test_rollout_metrics = _evaluate(torch, model, test_cases, rollout=True)

    val_track_metrics = _evaluate(torch, model, _filter_domain(val_cases, "track"), rollout=False)
    val_tunnel_metrics = _evaluate(torch, model, _filter_domain(val_cases, "tunnel"), rollout=False)
    test_track_metrics = _evaluate(torch, model, _filter_domain(test_cases, "track"), rollout=False)
    test_tunnel_metrics = _evaluate(torch, model, _filter_domain(test_cases, "tunnel"), rollout=False)

    overall_ok = bool(val_metrics["mae_pct"] <= float(args.max_val_mae_pct))
    if bool(args.enable_p95_gate):
        overall_ok = bool(overall_ok and val_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct))
    track_gate_pass = True
    if int(val_track_metrics["case_count"]) > 0:
        track_gate_pass = bool(val_track_metrics["mae_pct"] <= float(args.max_val_mae_pct_track))
        if bool(args.enable_p95_gate):
            track_gate_pass = bool(track_gate_pass and val_track_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct_track))
    tunnel_gate_pass = True
    if int(val_tunnel_metrics["case_count"]) > 0:
        tunnel_gate_pass = bool(val_tunnel_metrics["mae_pct"] <= float(args.max_val_mae_pct_tunnel))
        if bool(args.enable_p95_gate):
            tunnel_gate_pass = bool(tunnel_gate_pass and val_tunnel_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct_tunnel))
    rollout_gate_pass = bool(val_rollout_metrics["mae_pct"] <= float(args.max_val_rollout_mae_pct))

    contract_pass = bool(overall_ok and track_gate_pass and tunnel_gate_pass and rollout_gate_pass)
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
                "use_moving_load_attention": bool(args.use_moving_load_attention),
                "attention_gain": float(args.attention_gain),
                "physics_prior_weight": float(args.physics_prior_weight),
            },
        },
        ckpt_path,
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-train-tgnn-baseline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "dataset": str(args.dataset),
            "track_dataset": args.track_dataset,
            "tunnel_dataset": args.tunnel_dataset,
            "max_cases": int(args.max_cases),
            "epochs": int(args.epochs),
            "hidden_dim": int(args.hidden_dim),
            "lr": float(args.lr),
            "max_val_mae_pct": float(args.max_val_mae_pct),
            "max_val_mae_pct_track": float(args.max_val_mae_pct_track),
            "max_val_mae_pct_tunnel": float(args.max_val_mae_pct_tunnel),
            "enable_p95_gate": bool(args.enable_p95_gate),
            "max_val_mae_p95_pct": float(args.max_val_mae_p95_pct),
            "max_val_mae_p95_pct_track": float(args.max_val_mae_p95_pct_track),
            "max_val_mae_p95_pct_tunnel": float(args.max_val_mae_p95_pct_tunnel),
            "max_val_rollout_mae_pct": float(args.max_val_rollout_mae_pct),
            "seed": int(args.seed),
            "device": str(args.device),
            "allow_cpu_required": bool(args.allow_cpu_required),
            "enable_noise_augmentation": bool(args.enable_noise_augmentation),
            "train_sensor_noise_pct": float(args.train_sensor_noise_pct),
            "train_stiffness_noise_pct": float(args.train_stiffness_noise_pct),
            "robust_tail_q": float(args.robust_tail_q),
            "robust_tail_weight": float(args.robust_tail_weight),
            "use_moving_load_attention": bool(args.use_moving_load_attention),
            "attention_gain": float(args.attention_gain),
            "physics_prior_weight": float(args.physics_prior_weight),
        },
        "runtime": {
            "device_used": runtime_device,
            "cuda_available": cuda_available,
            "cpu_fallback_forbidden": cpu_fallback_forbidden,
            "cpu_used": cpu_used,
            "cpu_required": cpu_required,
            "cpu_fallback_used": cpu_fallback_used,
        },
        "domain_case_counts": domain_counts,
        "split_counts": {
            "train": len(train_cases),
            "val": len(val_cases),
            "test": len(test_cases),
        },
        "validation_metrics": val_metrics,
        "validation_rollout_metrics": val_rollout_metrics,
        "validation_track_metrics": val_track_metrics,
        "validation_tunnel_metrics": val_tunnel_metrics,
        "test_metrics": test_metrics,
        "test_rollout_metrics": test_rollout_metrics,
        "test_track_metrics": test_track_metrics,
        "test_tunnel_metrics": test_tunnel_metrics,
        "domain_checks": {
            "overall_val_gate_pass": overall_ok,
            "track_val_gate_pass": bool(track_gate_pass),
            "tunnel_val_gate_pass": bool(tunnel_gate_pass),
            "rollout_val_gate_pass": bool(rollout_gate_pass),
            "p95_gate_enabled": bool(args.enable_p95_gate),
            "overall_val_p95_gate_pass": bool(val_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct)),
            "track_val_p95_gate_pass": bool(
                int(val_track_metrics["case_count"]) == 0
                or val_track_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct_track)
            ),
            "tunnel_val_p95_gate_pass": bool(
                int(val_tunnel_metrics["case_count"]) == 0
                or val_tunnel_metrics["mae_pct_p95"] <= float(args.max_val_mae_p95_pct_tunnel)
            ),
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
    print(f"Wrote tgnn baseline report: {out}")
    print(f"Saved checkpoint: {ckpt_path}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
