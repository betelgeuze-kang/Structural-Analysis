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


def test_default_zero_copy_producer_stays_structural_scope() -> None:
    assert "engine_hook_stub.py" in probe.DEFAULT_PRODUCER_CMD
    assert ("md3" + "bead") not in probe.DEFAULT_PRODUCER_CMD.lower()
    assert ("rust_hip_" + "md3" + "bead_hook") not in probe.DEFAULT_PRODUCER_CMD.lower()

    result = probe.run(
        probe.DEFAULT_PRODUCER_CMD,
        require_rust_hip=False,
        allow_cpu_required=False,
        gpu_strict=True,
    )

    assert result["pass"] is True
    assert result["challenge_ok"] is True
    assert result["runtime_kind"] == "stub"
    assert result["runtime_backend"] == "structural_engine_stub"
