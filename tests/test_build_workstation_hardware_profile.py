from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_workstation_hardware_profile.py"
SPEC = importlib.util.spec_from_file_location("build_workstation_hardware_profile", SCRIPT_PATH)
assert SPEC is not None
build_workstation_hardware_profile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_workstation_hardware_profile)


def test_workstation_hardware_profile_schema_and_contract() -> None:
    payload = build_workstation_hardware_profile.build_workstation_hardware_profile(
        lscpu_text=(
            "Architecture: x86_64\n"
            "CPU(s): 12\n"
            "Thread(s) per core: 1\n"
            "Core(s) per socket: 12\n"
            "Socket(s): 1\n"
            "Vendor ID: AuthenticAMD\n"
            "Model name: AMD Ryzen 9 5900X 12-Core Processor\n"
        ),
        meminfo_text="MemTotal:       32600000 kB\nSwapTotal:      32000000 kB\n",
        lsblk_payload={
            "blockdevices": [
                {"name": "nvme0n1", "size": "1.8T", "type": "disk", "model": "FireCuda 520 SSD"}
            ]
        },
        lspci_text="0b:00.0 VGA compatible controller: Advanced Micro Devices, Inc. Navi 21 Radeon RX 6800\n",
        uname_text="Linux workstation 6.5.0 x86_64 GNU/Linux",
        os_release_text='NAME="Ubuntu"\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04.5 LTS"\n',
        viewer_probe_payload={"contract_pass": True, "summary_line": "viewer pass"},
    )

    assert payload["schema_version"] == "workstation-hardware-profile.v1"
    assert payload["contract_pass"] is True
    assert payload["hardware_profile"]["cpu"]["model_name"] == "AMD Ryzen 9 5900X 12-Core Processor"
    assert payload["hardware_profile"]["memory"]["total_gib"] > 30
    assert "Radeon RX 6800" in payload["hardware_profile"]["gpu"][0]["label"]
    assert payload["viewer_performance_probe"]["contract_pass"] is True


def test_workstation_hardware_profile_blocks_low_memory() -> None:
    payload = build_workstation_hardware_profile.build_workstation_hardware_profile(
        lscpu_text="CPU(s): 4\nModel name: Small CPU\n",
        meminfo_text="MemTotal:       1024 kB\n",
        lsblk_payload={"blockdevices": [{"name": "sda", "size": "20G", "type": "disk"}]},
        lspci_text="00:02.0 VGA compatible controller: Test GPU\n",
        uname_text="Linux test",
        os_release_text='NAME="TestOS"\n',
    )

    assert payload["contract_pass"] is False
    assert "memory_budget_below_16gib" in payload["blockers"]
