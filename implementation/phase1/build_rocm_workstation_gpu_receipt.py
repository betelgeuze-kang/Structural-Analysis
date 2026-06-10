#!/usr/bin/env python3
"""Build a local AMD ROCm/HIP workstation GPU receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


SCHEMA_VERSION = "rocm-workstation-gpu-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _resolve_tool_path(tool_name: str, fallback_paths: list[str] | tuple[str, ...] = ()) -> str:
    resolved = shutil.which(tool_name)
    if resolved:
        return resolved
    for candidate in fallback_paths:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return ""


def _run(cmd: list[str], *, timeout_s: float = 20.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "return_code": None,
            "timed_out": True,
            "stdout_excerpt": (exc.stdout or "")[:4000],
            "stderr_excerpt": (exc.stderr or "")[:4000],
        }
    except OSError as exc:
        return {
            "command": cmd,
            "return_code": None,
            "timed_out": False,
            "error": repr(exc),
            "stdout_excerpt": "",
            "stderr_excerpt": "",
        }
    return {
        "command": cmd,
        "return_code": proc.returncode,
        "timed_out": False,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "stdout_excerpt": (proc.stdout or "")[:4000],
        "stderr_excerpt": (proc.stderr or "")[:4000],
    }


def _parse_rocm_smi_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"cards": [], "system": {}, "parse_error": "empty_output"}
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"cards": [], "system": {}, "parse_error": str(exc)}
    cards: list[dict[str, Any]] = []
    system = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    for key, row in payload.items():
        if not str(key).startswith("card") or not isinstance(row, dict):
            continue
        cards.append(
            {
                "card_id": str(key),
                "card_series": row.get("Card series"),
                "card_model": row.get("Card model"),
                "card_vendor": row.get("Card vendor"),
                "card_sku": row.get("Card SKU"),
                "gpu_use_pct": row.get("GPU use (%)"),
                "vram_total_bytes": row.get("VRAM Total Memory (B)"),
                "vram_used_bytes": row.get("VRAM Total Used Memory (B)"),
                "temperature_edge_c": row.get("Temperature (Sensor edge) (C)"),
                "temperature_junction_c": row.get("Temperature (Sensor junction) (C)"),
                "temperature_memory_c": row.get("Temperature (Sensor memory) (C)"),
            }
        )
    return {"cards": cards, "system": system, "parse_error": ""}


def _parse_rocminfo(text: str) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"Agent\s+\d+", stripped):
            current = {"agent": stripped, "names": []}
            agents.append(current)
            continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "Name":
            current.setdefault("names", []).append(value)
            current.setdefault("name", value)
        elif key in {"Marketing Name", "Vendor Name", "Device Type", "Uuid"}:
            current[key.lower().replace(" ", "_")] = value
    gpu_agents = [agent for agent in agents if str(agent.get("device_type") or "").upper() == "GPU"]
    gfx_targets = sorted(
        {
            name
            for agent in gpu_agents
            for name in agent.get("names", [])
            if isinstance(name, str) and name.startswith("gfx")
        }
    )
    return {
        "agent_count": len(agents),
        "gpu_agents": gpu_agents,
        "gpu_agent_count": len(gpu_agents),
        "gfx_targets": gfx_targets,
    }


def _torch_rocm_probe() -> dict[str, Any]:
    probe: dict[str, Any] = {
        "torch_import_ok": False,
        "torch_rocm_runtime_ready": False,
        "torch_device_tensor_test_passed": False,
    }
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local runtime
        probe["error"] = repr(exc)
        return probe

    probe["torch_import_ok"] = True
    probe["torch_version"] = str(getattr(torch, "__version__", ""))
    probe["torch_version_hip"] = str(getattr(getattr(torch, "version", None), "hip", "") or "")
    try:
        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
        probe["torch_cuda_api_available"] = cuda_available
        probe["torch_cuda_device_count"] = device_count
        probe["device_names"] = [str(torch.cuda.get_device_name(idx)) for idx in range(min(device_count, 4))]
        if cuda_available and device_count > 0:
            value = torch.ones((1024,), device="cuda")
            total = (value * 2.0).sum()
            observed = float(total.detach().cpu())
            probe["torch_device_tensor_sum"] = observed
            probe["torch_device_tensor_device"] = str(total.device)
            probe["torch_device_tensor_test_passed"] = abs(observed - 2048.0) < 1.0e-6
    except Exception as exc:  # pragma: no cover - depends on local runtime
        probe["runtime_error"] = repr(exc)
    probe["torch_rocm_runtime_ready"] = bool(
        probe.get("torch_import_ok")
        and probe.get("torch_version_hip")
        and probe.get("torch_cuda_api_available")
        and probe.get("torch_device_tensor_test_passed")
    )
    return probe


def build_rocm_workstation_gpu_receipt() -> dict[str, Any]:
    tool_paths = {
        "rocm_smi": _resolve_tool_path(
            "rocm-smi",
            ("/opt/rocm/bin/rocm-smi", "/opt/rocm-6.0.2/bin/rocm-smi"),
        ),
        "rocminfo": _resolve_tool_path(
            "rocminfo",
            ("/opt/rocm/bin/rocminfo", "/opt/rocm-6.0.2/bin/rocminfo"),
        ),
        "hipcc": _resolve_tool_path(
            "hipcc",
            ("/opt/rocm/bin/hipcc", "/opt/rocm-6.0.2/bin/hipcc"),
        ),
        "hipconfig": _resolve_tool_path(
            "hipconfig",
            ("/opt/rocm/bin/hipconfig", "/opt/rocm-6.0.2/bin/hipconfig"),
        ),
        "amd_smi": _resolve_tool_path(
            "amd-smi",
            ("/opt/rocm/bin/amd-smi", "/opt/rocm-6.0.2/bin/amd-smi"),
        ),
        "nvidia_smi": _resolve_tool_path("nvidia-smi"),
    }
    kfd = Path("/dev/kfd")
    render_nodes = sorted(str(path) for path in Path("/dev/dri").glob("renderD*")) if Path("/dev/dri").is_dir() else []

    rocm_smi_result = (
        _run(
            [
                tool_paths["rocm_smi"],
                "--showproductname",
                "--showdriverversion",
                "--showmeminfo",
                "vram",
                "--showuse",
                "--showtemp",
                "--json",
            ],
            timeout_s=15.0,
        )
        if tool_paths["rocm_smi"]
        else {"return_code": None, "stdout": "", "stderr": "", "error": "rocm-smi_missing"}
    )
    rocminfo_result = (
        _run([tool_paths["rocminfo"]], timeout_s=20.0)
        if tool_paths["rocminfo"]
        else {"return_code": None, "stdout": "", "stderr": "", "error": "rocminfo_missing"}
    )
    rocm_smi = _parse_rocm_smi_json(str(rocm_smi_result.get("stdout") or ""))
    rocminfo = _parse_rocminfo(str(rocminfo_result.get("stdout") or ""))
    torch_probe = _torch_rocm_probe()

    rocm_hardware_ready = bool(
        kfd.exists()
        and render_nodes
        and (
            rocm_smi.get("cards")
            or rocminfo.get("gpu_agents")
        )
    )
    torch_rocm_ready = bool(torch_probe.get("torch_rocm_runtime_ready"))
    status = "ready" if rocm_hardware_ready and torch_rocm_ready else "partial" if rocm_hardware_ready else "blocked"
    blockers = []
    if not kfd.exists():
        blockers.append("dev_kfd_missing")
    if not render_nodes:
        blockers.append("render_node_missing")
    if not (rocm_smi.get("cards") or rocminfo.get("gpu_agents")):
        blockers.append("rocm_gpu_agent_not_detected")
    if not torch_rocm_ready:
        blockers.append("torch_rocm_runtime_not_ready")

    device_names = list(torch_probe.get("device_names") or [])
    if not device_names:
        device_names = [
            str(agent.get("marketing_name") or agent.get("name") or "")
            for agent in rocminfo.get("gpu_agents", [])
            if isinstance(agent, dict)
        ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "rocm_hardware_ready": rocm_hardware_ready,
        "torch_rocm_runtime_ready": torch_rocm_ready,
        "target_hardware_match": any("6900" in name for name in device_names)
        or any("6900" in str(card.get("card_series") or "") for card in rocm_smi.get("cards", [])),
        "device_names": device_names,
        "gfx_targets": rocminfo.get("gfx_targets", []),
        "tool_paths": tool_paths,
        "device_nodes": {
            "dev_kfd_present": kfd.exists(),
            "render_nodes": render_nodes,
        },
        "rocm_smi": {
            "return_code": rocm_smi_result.get("return_code"),
            "cards": rocm_smi.get("cards", []),
            "system": rocm_smi.get("system", {}),
            "parse_error": rocm_smi.get("parse_error", ""),
            "stderr_excerpt": rocm_smi_result.get("stderr_excerpt", ""),
        },
        "rocminfo": {
            "return_code": rocminfo_result.get("return_code"),
            "gpu_agent_count": rocminfo.get("gpu_agent_count", 0),
            "gpu_agents": rocminfo.get("gpu_agents", []),
            "gfx_targets": rocminfo.get("gfx_targets", []),
            "stderr_excerpt": rocminfo_result.get("stderr_excerpt", ""),
        },
        "torch_rocm_probe": torch_probe,
        "pytorch_device_label_policy": (
            "PyTorch ROCm exposes HIP devices through the torch.cuda API; a device label such as cuda:0 "
            "can still be AMD ROCm/HIP when torch.version.hip is populated and rocm-smi/rocminfo detect AMD GPU."
        ),
        "nvidia_smi_not_required_for_amd_rocm": True,
        "claim_boundary": (
            "This receipt proves local AMD ROCm/PyTorch-HIP workstation availability. It does not prove that every "
            "MGT full sparse frame/shell solver artifact is GPU accelerated unless that artifact records a ROCm/HIP backend."
        ),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "gpu_rocm_workstation_receipt.json",
    )
    args = parser.parse_args()
    payload = build_rocm_workstation_gpu_receipt()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "rocm-workstation-gpu: "
        f"{payload['status']} device={','.join(payload.get('device_names') or []) or 'unknown'} "
        f"torch_rocm={payload['torch_rocm_runtime_ready']} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
