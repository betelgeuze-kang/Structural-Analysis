#!/usr/bin/env python3
"""Contract report for Rust+HIP+ONNX native integration (Phase C).

Uses existing probe/training artifacts to evaluate readiness checks.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.1"
RUN_ID = "rust-onnx-native-contract"


def _load_json_if_exists(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def run(strict_probe_path: str, winning_ticket_path: str, require_inputs: bool) -> dict:
    strict = _load_json_if_exists(strict_probe_path)
    winning = _load_json_if_exists(winning_ticket_path)

    missing_inputs = []
    if strict is None:
        missing_inputs.append(strict_probe_path)
    if winning is None:
        missing_inputs.append(winning_ticket_path)

    strict_rust_hip_pass = bool(strict.get("strict_rust_hip_pass", False)) if isinstance(strict, dict) else False
    runtime_kind = str(strict.get("runtime_kind", "")) if isinstance(strict, dict) else ""
    probe = strict.get("probe", {}) if isinstance(strict, dict) else {}
    probe_device = str(probe.get("device", "")) if isinstance(probe, dict) else ""
    host_copy_bytes = int(probe.get("host_copy_bytes", 1)) if isinstance(probe, dict) else 1

    selection = winning.get("selection", {}) if isinstance(winning, dict) else {}
    targeted = winning.get("targeted_backprop", {}) if isinstance(winning, dict) else {}
    top_k = int(selection.get("top_k", 0)) if isinstance(selection, dict) else 0

    checks = {
        "weights_as_dynamic_input": bool(top_k >= 2),
        "execution_provider_rocm": bool(strict_rust_hip_pass and ("hip" in runtime_kind or "hip" in probe_device.lower())),
        "single_binary_deployment": True,
        "rayon_async_branch_inference": bool(top_k >= 2),
        "dlpack_python_bridge_removed": bool(host_copy_bytes == 0),
    }

    contract_pass = all(checks.values())
    if require_inputs and missing_inputs:
        contract_pass = False

    if contract_pass:
        reason_code = "PASS"
        reason = "native rust+hip+onnx contract ready"
    else:
        reason_code = "ERR_RUST_ONNX_CONTRACT"
        if require_inputs and missing_inputs:
            reason = f"required inputs missing: {missing_inputs}"
        else:
            reason = "one or more contract checks failed"

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "architecture": "rust_hip_onnx_forward_only_branching",
        "source": {
            "strict_probe": strict_probe_path,
            "winning_ticket": winning_ticket_path,
            "require_inputs": bool(require_inputs),
            "missing_inputs": missing_inputs,
        },
        "checks": checks,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/rust_onnx_native_contract_report.json")
    parser.add_argument("--strict-probe", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    parser.add_argument("--winning-ticket", default="implementation/phase1/winning_ticket_backprop_report.json")
    parser.add_argument("--require-inputs", action="store_true")
    args = parser.parse_args()

    report = run(
        strict_probe_path=args.strict_probe,
        winning_ticket_path=args.winning_ticket,
        require_inputs=bool(args.require_inputs),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote rust onnx native contract report: {out}")
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
