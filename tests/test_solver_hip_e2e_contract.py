from __future__ import annotations

from implementation.phase1.run_solver_hip_e2e_contract import run_solver_hip_e2e_contract


def test_solver_hip_e2e_contract_passes_with_gpu_telemetry(monkeypatch) -> None:
    gpu_runtime = {
        "main_loop_backend": "rocm_hip_kernel",
        "runtime_backend": "rocm_hip_kernel",
        "cpu_backend": False,
        "cpu_required": False,
        "cpu_fallback_used": False,
        "hip_kernel_invocation_count": 4,
        "host_copy_bytes": 0,
        "device_residency_ratio": 1.0,
        "solver_path_kind": "production_hip_kernel",
        "production_kernel_path": True,
        "force_jacobian_kernel_consistent": True,
        "surrogate_runtime_used": False,
        "simplified_runtime_used": False,
        "surrogate_runtime_markers": [],
    }

    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame", "status": 0, "converged": True, "runtime": dict(gpu_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame_ndtha",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame_ndtha", "status": 0, "converged_all_steps": True, "runtime": dict(gpu_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_track_point_load",
        lambda _cfg: {"backend": "rust_ffi_kernel", "status_code": 0, "converged": True, "runtime": dict(gpu_runtime)},
    )

    report = run_solver_hip_e2e_contract(
        strict_probe={
            "pass": True,
            "gpu_strict_pass": True,
            "cpu_required": False,
            "cpu_fallback_used": False,
            "runtime_backend": "rocm_torch",
        },
        min_device_residency_ratio=0.99,
    )
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["all_main_loops_gpu_pass"] is True
    assert report["checks"]["all_production_kernel_pass"] is True
    assert report["checks"]["no_surrogate_runtime_markers_pass"] is True
    assert report["checks"]["all_force_jacobian_consistent_pass"] is True
    assert report["checks"]["hazard_topology_diversity_pass"] is True
    assert report["summary"]["solver_count"] == 20
    assert report["summary"]["hazard_family_count"] >= 14
    assert report["summary"]["topology_family_count"] >= 12
    assert report["summary"]["load_path_family_count"] >= 12


def test_solver_hip_e2e_contract_fails_on_cpu_runtime(monkeypatch) -> None:
    cpu_runtime = {
        "main_loop_backend": "rust_ffi_cpu",
        "runtime_backend": "rust_ffi_cpu",
        "cpu_backend": True,
        "cpu_required": True,
        "cpu_fallback_used": False,
        "hip_kernel_invocation_count": 0,
        "host_copy_bytes": 0,
        "device_residency_ratio": 0.0,
        "solver_path_kind": "cpu_fallback_runtime",
        "production_kernel_path": False,
        "force_jacobian_kernel_consistent": False,
        "surrogate_runtime_used": False,
        "simplified_runtime_used": False,
        "surrogate_runtime_markers": [],
    }

    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame", "status": 0, "converged": True, "runtime": dict(cpu_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame_ndtha",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame_ndtha", "status": 0, "converged_all_steps": True, "runtime": dict(cpu_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_track_point_load",
        lambda _cfg: {"backend": "rust_ffi_kernel", "status_code": 0, "converged": True, "runtime": dict(cpu_runtime)},
    )

    report = run_solver_hip_e2e_contract(
        strict_probe={
            "pass": True,
            "gpu_strict_pass": True,
            "cpu_required": False,
            "cpu_fallback_used": False,
            "runtime_backend": "rocm_torch",
        },
        min_device_residency_ratio=0.99,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_NONLINEAR_FRAME_GPU_FAIL"
    assert report["checks"]["all_main_loops_gpu_pass"] is False


def test_solver_hip_e2e_contract_fails_on_surrogate_runtime(monkeypatch) -> None:
    surrogate_runtime = {
        "main_loop_backend": "rocm_hip_kernel",
        "runtime_backend": "rocm_hip_kernel",
        "cpu_backend": False,
        "cpu_required": False,
        "cpu_fallback_used": False,
        "hip_kernel_invocation_count": 4,
        "host_copy_bytes": 0,
        "device_residency_ratio": 1.0,
        "solver_path_kind": "surrogate_runtime",
        "production_kernel_path": False,
        "force_jacobian_kernel_consistent": False,
        "surrogate_runtime_used": True,
        "simplified_runtime_used": True,
        "surrogate_runtime_markers": ["surrogate_runtime"],
    }

    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame", "status": 0, "converged": True, "runtime": dict(surrogate_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_nonlinear_frame_ndtha",
        lambda **_kwargs: {"backend": "rust_ffi_nonlinear_frame_ndtha", "status": 0, "converged_all_steps": True, "runtime": dict(surrogate_runtime)},
    )
    monkeypatch.setattr(
        "implementation.phase1.run_solver_hip_e2e_contract.solve_track_point_load",
        lambda _cfg: {"backend": "rust_ffi_kernel", "status_code": 0, "converged": True, "runtime": dict(surrogate_runtime)},
    )

    report = run_solver_hip_e2e_contract(
        strict_probe={
            "pass": True,
            "gpu_strict_pass": True,
            "cpu_required": False,
            "cpu_fallback_used": False,
            "runtime_backend": "rocm_torch",
        },
        min_device_residency_ratio=0.99,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_PRODUCTION_KERNEL_FAIL"
    assert report["checks"]["all_production_kernel_pass"] is False
    assert report["checks"]["no_surrogate_runtime_markers_pass"] is False
