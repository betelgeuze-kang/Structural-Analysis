#!/usr/bin/env python3
"""Capture the local workstation hardware profile for delivery service gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA_VERSION = "workstation-hardware-profile.v1"
DEFAULT_PROFILE_OUT = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_row(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "available": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": _sha256_path(path) if path.exists() else "",
    }


def _run_text(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _parse_key_value_lines(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        rows[key.strip()] = value.strip()
    return rows


def _parse_os_release(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        rows[key.strip()] = value.strip().strip('"')
    return rows


def _parse_meminfo(meminfo_text: str) -> dict[str, Any]:
    rows = _parse_key_value_lines(meminfo_text)
    total_kib = 0
    if "MemTotal" in rows:
        match = re.search(r"(\d+)", rows["MemTotal"])
        total_kib = int(match.group(1)) if match else 0
    swap_kib = 0
    if "SwapTotal" in rows:
        match = re.search(r"(\d+)", rows["SwapTotal"])
        swap_kib = int(match.group(1)) if match else 0
    return {
        "total_kib": total_kib,
        "total_gib": round(total_kib / (1024 * 1024), 2) if total_kib else 0.0,
        "swap_total_kib": swap_kib,
        "swap_total_gib": round(swap_kib / (1024 * 1024), 2) if swap_kib else 0.0,
    }


def _parse_cpu(lscpu_text: str) -> dict[str, Any]:
    rows = _parse_key_value_lines(lscpu_text)

    def _int(key: str) -> int:
        value = rows.get(key, "0")
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else 0

    return {
        "model_name": rows.get("Model name", ""),
        "architecture": rows.get("Architecture", ""),
        "cpu_count": _int("CPU(s)"),
        "threads_per_core": _int("Thread(s) per core"),
        "cores_per_socket": _int("Core(s) per socket"),
        "socket_count": _int("Socket(s)"),
        "vendor_id": rows.get("Vendor ID", ""),
        "flags_present": bool(rows.get("Flags")),
    }


def _parse_gpus(lspci_text: str) -> list[dict[str, Any]]:
    gpus = []
    for line in lspci_text.splitlines():
        lowered = line.lower()
        if " vga " not in lowered and "3d controller" not in lowered and "display controller" not in lowered:
            continue
        _, _, label = line.partition(": ")
        gpus.append({"label": label or line, "source": "lspci"})
    return gpus


def _parse_storage(lsblk_payload: dict[str, Any]) -> list[dict[str, Any]]:
    devices = []
    for row in lsblk_payload.get("blockdevices", []) if isinstance(lsblk_payload, dict) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("type", "")).lower() not in {"disk", "nvme", "ssd"}:
            continue
        devices.append(
            {
                "name": str(row.get("name", "")),
                "size": str(row.get("size", "")),
                "type": str(row.get("type", "")),
                "model": str(row.get("model", "") or ""),
                "mountpoint": str(row.get("mountpoint", "") or ""),
                "fstype": str(row.get("fstype", "") or ""),
            }
        )
    return devices


def _load_lsblk_payload(lsblk_text: str) -> dict[str, Any]:
    if not lsblk_text:
        return {}
    try:
        payload = json.loads(lsblk_text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _viewer_probe_summary(path: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    probe_payload = payload if payload is not None else _load_json(path)
    probe = probe_payload.get("probe", {}) if isinstance(probe_payload.get("probe"), dict) else {}
    raf = probe.get("rafSample", {}) if isinstance(probe.get("rafSample"), dict) else {}
    return {
        "path": str(path),
        "available": bool(probe_payload),
        "contract_pass": bool(probe_payload.get("contract_pass", False)),
        "ready_ms": probe.get("readyMs"),
        "average_fps": raf.get("averageFps"),
        "summary_line": str(probe_payload.get("summary_line", "")),
        "claim_boundary": str(probe_payload.get("claim_boundary", "")),
    }


def build_workstation_hardware_profile(
    *,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    lscpu_text: str | None = None,
    meminfo_text: str | None = None,
    lsblk_payload: dict[str, Any] | None = None,
    lspci_text: str | None = None,
    uname_text: str | None = None,
    os_release_text: str | None = None,
    viewer_probe_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lscpu_text = lscpu_text if lscpu_text is not None else _run_text(["lscpu"])
    meminfo_text = meminfo_text if meminfo_text is not None else _read_text(Path("/proc/meminfo"))
    if lsblk_payload is None:
        lsblk_payload = _load_lsblk_payload(_run_text(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL"]))
    lspci_text = lspci_text if lspci_text is not None else _run_text(["lspci"])
    uname_text = uname_text if uname_text is not None else _run_text(["uname", "-a"])
    os_release_text = os_release_text if os_release_text is not None else _read_text(Path("/etc/os-release"))

    cpu = _parse_cpu(lscpu_text)
    memory = _parse_meminfo(meminfo_text)
    os_release = _parse_os_release(os_release_text)
    storage_devices = _parse_storage(lsblk_payload)
    gpus = _parse_gpus(lspci_text)
    viewer_summary = _viewer_probe_summary(viewer_browser_performance_probe, viewer_probe_payload)

    blockers = [
        *(["cpu_model_missing"] if not cpu["model_name"] else []),
        *(["cpu_core_budget_below_minimum"] if int(cpu["cpu_count"] or 0) < 4 else []),
        *(["memory_budget_below_16gib"] if float(memory["total_gib"] or 0.0) < 16.0 else []),
        *(["gpu_not_detected"] if not gpus else []),
        *(["storage_device_not_detected"] if not storage_devices else []),
        *(["os_release_not_detected"] if not os_release and not uname_text else []),
    ]
    warnings = [
        *(["viewer_performance_probe_not_attached"] if not viewer_summary["available"] else []),
        *(
            ["viewer_performance_probe_not_green"]
            if viewer_summary["available"] and not viewer_summary["contract_pass"]
            else []
        ),
    ]
    contract_pass = not blockers
    model_name = str(cpu["model_name"] or "unknown CPU")
    memory_gib = float(memory["total_gib"] or 0.0)
    gpu_label = gpus[0]["label"] if gpus else "unknown GPU"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_WORKSTATION_HARDWARE_PROFILE_BLOCKED",
        "summary_line": (
            f"Workstation hardware profile: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"cpu={model_name} | ram={memory_gib:.1f}GiB | gpu={gpu_label}"
        ),
        "profile_scope": {
            "service_model": "single_operator_workstation_delivery",
            "customer_device_performance_claim": False,
            "multi_tenant_saas_claim": False,
        },
        "hardware_profile": {
            "cpu": cpu,
            "memory": memory,
            "gpu": gpus,
            "storage": storage_devices,
            "os": {
                "name": os_release.get("PRETTY_NAME") or os_release.get("NAME", ""),
                "id": os_release.get("ID", ""),
                "version": os_release.get("VERSION_ID", ""),
                "kernel": uname_text,
            },
        },
        "viewer_performance_probe": viewer_summary,
        "recommended_max_project_size": {
            "small": {"max_nodes": 25000, "max_elements": 50000, "delivery_class": "same_session"},
            "medium": {"max_nodes": 75000, "max_elements": 150000, "delivery_class": "standard"},
            "large": {"max_nodes": 150000, "max_elements": 300000, "delivery_class": "batch_or_overnight"},
            "oversize": {"delivery_class": "split_or_quote_required"},
        },
        "unsupported_conditions": [
            "multi_tenant_saas_operation",
            "customer_device_fps_claims",
            "autonomous_structural_engineer_replacement_claims",
            "projects_above_oversize_budget_without_split_or_quote",
        ],
        "warnings": warnings,
        "blockers": blockers,
        "source_rows": [
            _source_row("viewer_browser_performance_probe", viewer_browser_performance_probe),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_PROFILE_OUT)
    parser.add_argument(
        "--viewer-browser-performance-probe",
        type=Path,
        default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_workstation_hardware_profile(
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
