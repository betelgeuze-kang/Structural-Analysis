#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_rocm_workstation_gpu_receipt import (  # noqa: E402
    _parse_rocminfo,
    _parse_rocm_smi_json,
    _resolve_tool_path,
)


def test_parse_rocm_smi_json_extracts_6900xt_card() -> None:
    payload = _parse_rocm_smi_json(
        json.dumps(
            {
                "card0": {
                    "Card series": "Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]",
                    "Card model": "0x2408",
                    "Card vendor": "Advanced Micro Devices, Inc. [AMD/ATI]",
                    "GPU use (%)": "4",
                    "VRAM Total Memory (B)": "17163091968",
                },
                "system": {"Driver version": "6.5.0-26-generic"},
            }
        )
    )
    assert payload["parse_error"] == ""
    assert payload["cards"][0]["card_id"] == "card0"
    assert "6900 XT" in payload["cards"][0]["card_series"]
    assert payload["system"]["Driver version"] == "6.5.0-26-generic"


def test_parse_rocminfo_extracts_gfx1030_gpu_agent() -> None:
    payload = _parse_rocminfo(
        """
HSA Agents
Agent 1
  Name:                    AMD Ryzen 9 5900X 12-Core Processor
  Marketing Name:          AMD Ryzen 9 5900X 12-Core Processor
  Vendor Name:             CPU
  Device Type:             CPU
Agent 2
  Name:                    gfx1030
  Marketing Name:          AMD Radeon RX 6900 XT
  Vendor Name:             AMD
  Device Type:             GPU
      Name:                    amdgcn-amd-amdhsa--gfx1030
"""
    )
    assert payload["gpu_agent_count"] == 1
    assert payload["gpu_agents"][0]["marketing_name"] == "AMD Radeon RX 6900 XT"
    assert payload["gfx_targets"] == ["gfx1030"]


def test_resolve_tool_path_uses_rocm_fallback_when_path_lookup_misses(tmp_path: Path) -> None:
    fallback = tmp_path / "hipcc"
    fallback.write_text("#!/bin/sh\n", encoding="utf-8")
    fallback.chmod(0o755)

    resolved = _resolve_tool_path(
        "definitely-not-a-real-tool-6900xt-test",
        (str(fallback),),
    )

    assert resolved == str(fallback)
