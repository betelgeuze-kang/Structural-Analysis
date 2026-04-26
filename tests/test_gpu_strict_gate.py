from __future__ import annotations

import zero_copy_real_probe as probe


def _base_probe_payload() -> dict:
    return {
        "roundtrip_success": True,
        "shared_storage": True,
        "host_copy_bytes": 0,
        "shape": [256, 4],
        "dtype": "float32",
        "strides": [4, 1],
        "byte_offset": 0,
        "challenge_echo": "abc",
        "tensor_bytes": 4096,
        "compute_seconds": 0.001,
        "host_copy_seconds": 0.0,
        "serialization_seconds": 0.0002,
        "producer_kind": "rust_hip",
    }


def test_gpu_strict_fails_on_cpu_backend(monkeypatch) -> None:
    def fake_run_json_cmd(command: str, payload: dict) -> dict:
        data = _base_probe_payload()
        data.update(
            {
                "challenge_echo": payload["challenge"],
                "runtime_backend": "cpu",
                "device": "cpu",
                "cpu_required": False,
            }
        )
        return data

    monkeypatch.setattr(probe, "_run_json_cmd", fake_run_json_cmd)
    result = probe.run("dummy", require_rust_hip=False, allow_cpu_required=False, gpu_strict=True)
    assert result["gpu_strict_pass"] is False
    assert result["pass"] is False


def test_gpu_strict_passes_on_gpu_backend(monkeypatch) -> None:
    def fake_run_json_cmd(command: str, payload: dict) -> dict:
        data = _base_probe_payload()
        data.update(
            {
                "challenge_echo": payload["challenge"],
                "runtime_backend": "rocm",
                "device": "cuda:0",
                "cpu_required": False,
            }
        )
        return data

    monkeypatch.setattr(probe, "_run_json_cmd", fake_run_json_cmd)
    result = probe.run("dummy", require_rust_hip=True, allow_cpu_required=False, gpu_strict=True)
    assert result["gpu_strict_pass"] is True
    assert result["strict_rust_hip_pass"] is True
    assert result["pass"] is True
