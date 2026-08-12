#ifndef STRUCTURAL_HIP_NONLINEAR_STATIC_HIP_HPP
#define STRUCTURAL_HIP_NONLINEAR_STATIC_HIP_HPP

#include "../solver_cpu/nonlinear_static.hpp"

#include <cstdint>
#include <string>

namespace structural::hip {

/// Source-, toolchain-, and device-bound receipt for one no-fallback HIP Newton execution.
struct NonlinearStaticExecutionReceipt {
    std::int32_t device_id;
    std::string device_name;
    std::string architecture;
    std::int32_t runtime_version;
    std::int32_t driver_version;
    std::string compiler_version;
    std::string compiled_architectures;
    std::string kernel_source_sha256;
    std::string device_library_sha256;
    std::string execution_profile;
    std::uint64_t h2d_bytes;
    std::uint64_t d2h_bytes;
    std::uint64_t h2d_transfer_count;
    std::uint64_t d2h_transfer_count;
    std::uint64_t synchronization_count;
    std::uint64_t kernel_launch_count;
    std::uint64_t device_buffer_bytes;
    std::uint64_t vram_total_bytes;
    std::uint64_t vram_free_before_bytes;
    std::uint64_t vram_free_after_alloc_bytes;
    std::uint32_t fallback_count;
    bool fp64;
    bool deterministic;
    bool device_resident_model;
    bool device_resident_newton_state;
    bool device_resident_tangent_solve;
    bool device_result_recovery;
    std::uint64_t host_intermediate_state_transfer_count;
    std::uint64_t host_iteration_control_transfer_count;
};

struct NonlinearStaticHipExecution {
    solver_cpu::NonlinearStaticResult result;
    NonlinearStaticExecutionReceipt receipt;
};

/*
 * Solve one bounded story-frame problem with model data, constitutive assembly, Newton state,
 * tridiagonal tangent solves, line search and result recovery resident on the selected HIP
 * device. Validation is shared with the CPU reference source. Any HIP failure throws; no CPU
 * solve or fallback branch exists.
 */
[[nodiscard]] NonlinearStaticHipExecution solve_nonlinear_static_hip(
    const solver_cpu::NonlinearStaticConfig& config,
    const solver_cpu::NonlinearStaticInputs& inputs);

}  // namespace structural::hip

#endif
