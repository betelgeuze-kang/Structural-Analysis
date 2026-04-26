#!/usr/bin/env python3
"""Step-4: train neural-operator style surrogate for dynamic global response."""

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


from spatiotemporal_dataset_utils import load_jsonl, MATERIALS, TOPOLOGIES  # noqa: E402


REASONS = {
    "PASS": "neural-operator surrogate trained",
    "ERR_DATASET_EMPTY": "dataset is empty",
    "ERR_METRIC_FAIL": "validation metric threshold failed",
}


class SpectralConv1d:
    def __init__(self, torch, in_channels: int, out_channels: int, modes: int):
        self.modes = int(modes)
        scale = 1.0 / max(1, in_channels * out_channels)
        w = scale * torch.randn(in_channels, out_channels, self.modes, 2, dtype=torch.float32)
        self.weight = torch.nn.Parameter(w)

    def parameters(self):
        yield self.weight

    def to(self, device):
        self.weight.data = self.weight.data.to(device)
        return self

    def __call__(self, torch, x):
        # x: [B, C, T]
        x_ft = torch.fft.rfft(x, dim=-1)
        b, _, t_ft = x_ft.shape
        out_ft = torch.zeros(b, self.weight.shape[1], t_ft, dtype=torch.cfloat, device=x.device)
        m = min(self.modes, t_ft)
        w = torch.view_as_complex(self.weight[:, :, :m, :].contiguous())  # [Cin, Cout, M]
        out_ft[:, :, :m] = torch.einsum("bcm,com->bom", x_ft[:, :, :m], w)
        return torch.fft.irfft(out_ft, n=x.shape[-1], dim=-1)


class FNO1DSurrogate:
    def __init__(self, torch, in_channels: int, width: int, modes: int):
        nn = torch.nn
        self.in_proj = nn.Conv1d(in_channels, width, kernel_size=1)
        self.spec1 = SpectralConv1d(torch, width, width, modes=modes)
        self.spec2 = SpectralConv1d(torch, width, width, modes=modes)
        self.w1 = nn.Conv1d(width, width, kernel_size=1)
        self.w2 = nn.Conv1d(width, width, kernel_size=1)
        self.out_proj = nn.Conv1d(width, 1, kernel_size=1)
        self._modules = [self.in_proj, self.w1, self.w2, self.out_proj]

    def parameters(self):
        for m in self._modules:
            for p in m.parameters():
                yield p
        for p in self.spec1.parameters():
            yield p
        for p in self.spec2.parameters():
            yield p

    def state_dict(self):
        return {
            "in_proj": self.in_proj.state_dict(),
            "w1": self.w1.state_dict(),
            "w2": self.w2.state_dict(),
            "out_proj": self.out_proj.state_dict(),
            "spec1_weight": self.spec1.weight.detach().cpu(),
            "spec2_weight": self.spec2.weight.detach().cpu(),
        }

    def to(self, device):
        for m in self._modules:
            m.to(device)
        self.spec1.to(device)
        self.spec2.to(device)
        return self

    def train(self):
        for m in self._modules:
            m.train()

    def eval(self):
        for m in self._modules:
            m.eval()

    def forward(self, torch, x):
        # x: [B, Cin, T]
        x = self.in_proj(x)
        x = torch.relu(self.spec1(torch, x) + self.w1(x))
        x = torch.relu(self.spec2(torch, x) + self.w2(x))
        y = self.out_proj(x)
        return y[:, 0, :]


def _split_cases(cases: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    train = [c for c in cases if c.get("split") == "train"]
    val = [c for c in cases if c.get("split") == "val"]
    test = [c for c in cases if c.get("split") == "test"]
    return train, val, test


def _one_hot(index: int, size: int) -> list[float]:
    out = [0.0 for _ in range(size)]
    out[index] = 1.0
    return out


def _prepare_case(case: dict) -> tuple[list[float], list[float], list[float]]:
    gm = [float(v) for v in case["ground_motion_g"]]
    resp = case["response_u"]
    global_resp = [sum(float(v) for v in row) / max(1, len(row)) for row in resp]
    topo_idx = TOPOLOGIES.index(str(case["topology_type"]))
    mat_idx = MATERIALS.index(str(case["material_type"]))
    cond = _one_hot(topo_idx, len(TOPOLOGIES)) + _one_hot(mat_idx, len(MATERIALS))
    return gm, global_resp, cond


def _build_batch(torch, batch_cases: list[dict]):
    seq_len = int(batch_cases[0]["seq_len"])
    cond_dim = len(TOPOLOGIES) + len(MATERIALS)
    x = torch.zeros(len(batch_cases), 1 + cond_dim, seq_len, dtype=torch.float32)
    y = torch.zeros(len(batch_cases), seq_len, dtype=torch.float32)
    for i, case in enumerate(batch_cases):
        gm, global_resp, cond = _prepare_case(case)
        x[i, 0, :] = torch.tensor(gm, dtype=torch.float32)
        for j, c in enumerate(cond):
            x[i, 1 + j, :] = float(c)
        y[i, :] = torch.tensor(global_resp, dtype=torch.float32)
    return x, y


def _evaluate(torch, model: FNO1DSurrogate, cases: list[dict], batch_size: int) -> dict:
    if not cases:
        return {"case_count": 0, "mae_pct": 0.0, "peak_error_pct": 0.0}
    model.eval()
    abs_err = 0.0
    abs_ref = 0.0
    peak = []
    with torch.no_grad():
        for i in range(0, len(cases), batch_size):
            batch = cases[i : i + batch_size]
            x, y = _build_batch(torch, batch)
            pred = model.forward(torch, x)
            e = torch.abs(pred - y)
            r = torch.abs(y)
            abs_err += float(e.sum().item())
            abs_ref += float(r.sum().item())
            p = float(torch.max(e).item())
            rr = float(torch.max(r).item())
            peak.append(100.0 * p / max(1e-9, rr))
    return {
        "case_count": len(cases),
        "mae_pct": 100.0 * abs_err / max(1e-9, abs_ref),
        "peak_error_pct": sum(peak) / max(1, len(peak)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--out", default="implementation/phase1/spatiotemporal_data/neural_operator_report.json")
    p.add_argument("--ckpt", default="implementation/phase1/spatiotemporal_data/neural_operator.pt")
    p.add_argument("--max-cases", type=int, default=1000)
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=12)
    p.add_argument("--width", type=int, default=48)
    p.add_argument("--modes", type=int, default=24)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--max-val-mae-pct", type=float, default=80.0)
    p.add_argument("--seed", type=int, default=23)
    args = p.parse_args()

    torch, F = _require_torch()
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))

    cases = load_jsonl(Path(args.dataset), max_cases=int(args.max_cases))
    if not cases:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-neural-operator",
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

    in_channels = 1 + len(TOPOLOGIES) + len(MATERIALS)
    model = FNO1DSurrogate(torch, in_channels=in_channels, width=int(args.width), modes=int(args.modes)).to("cpu")
    optimizer = torch.optim.Adam(list(model.parameters()), lr=float(args.lr))
    history = []

    for ep in range(int(args.epochs)):
        model.train()
        random.shuffle(train_cases)
        loss_sum = 0.0
        steps = 0
        for i in range(0, len(train_cases), int(args.batch_size)):
            batch = train_cases[i : i + int(args.batch_size)]
            if not batch:
                continue
            x, y = _build_batch(torch, batch)
            pred = model.forward(torch, x)
            loss = F.mse_loss(pred, y)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(model.parameters()), max_norm=1.0)
            optimizer.step()
            loss_sum += float(loss.detach().item())
            steps += 1
        val_eval = _evaluate(torch, model, val_cases, batch_size=max(1, int(args.batch_size)))
        history.append(
            {
                "epoch": ep + 1,
                "train_loss": loss_sum / max(1, steps),
                "val_mae_pct": val_eval["mae_pct"],
                "val_peak_error_pct": val_eval["peak_error_pct"],
            }
        )

    val_metrics = _evaluate(torch, model, val_cases, batch_size=max(1, int(args.batch_size)))
    test_metrics = _evaluate(torch, model, test_cases, batch_size=max(1, int(args.batch_size)))
    contract_pass = bool(val_metrics["mae_pct"] <= float(args.max_val_mae_pct))
    reason_code = "PASS" if contract_pass else "ERR_METRIC_FAIL"

    ckpt_path = Path(args.ckpt)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "meta": {
                "width": int(args.width),
                "modes": int(args.modes),
                "epochs": int(args.epochs),
                "seed": int(args.seed),
            },
        },
        ckpt_path,
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-train-neural-operator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "dataset": args.dataset,
            "max_cases": int(args.max_cases),
            "epochs": int(args.epochs),
            "batch_size": int(args.batch_size),
            "width": int(args.width),
            "modes": int(args.modes),
            "lr": float(args.lr),
            "seed": int(args.seed),
        },
        "split_counts": {"train": len(train_cases), "val": len(val_cases), "test": len(test_cases)},
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "history_tail": history[-5:],
        "checkpoint": str(ckpt_path),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote neural operator report: {out}")
    print(f"Saved checkpoint: {ckpt_path}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
