#ifndef STRUCTURAL_HIP_NONLINEAR_NDTHA_HIP_HPP
#define STRUCTURAL_HIP_NONLINEAR_NDTHA_HIP_HPP

#include "../solver_cpu/nonlinear_ndtha.hpp"

#include <cstdint>
#include <string>

namespace structural::hip {

/// Source-, toolchain-, and device-bound receipt for one no-fallback HIP NDTHA
/// execution.
struct NonlinearNdthaExecutionReceipt {
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
    bool device_resident_step_state;
    bool device_resident_newmark_newton;
    bool device_resident_tangent_solve;
    bool device_result_recovery;
    std::uint64_t host_intermediate_state_transfer_count;
    std::uint64_t host_iteration_control_transfer_count;
    std::uint64_t host_step_control_transfer_count;
};

struct NonlinearNdthaHipExecution {
    solver_cpu::NonlinearNdthaResult result;
    NonlinearNdthaExecutionReceipt receipt;
};

/*
 * Execute one bounded story-frame NDTHA case with model, step state, adaptive
 * loading, Newmark/Newton iterations, tangent solves, collapse checks and all
 * response recovery resident on the selected HIP device. Any HIP failure
 * throws; no CPU solve or fallback branch exists.
 */
[[nodiscard]] NonlinearNdthaHipExecution
solve_nonlinear_ndtha_hip(const solver_cpu::NonlinearNdthaConfig& config,
                          const solver_cpu::NonlinearNdthaInputs& inputs);

} // namespace structural::hip

#endif
