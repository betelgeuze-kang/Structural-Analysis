#ifndef STRUCTURAL_HIP_SPARSE_LINEAR_HIP_HPP
#define STRUCTURAL_HIP_SPARSE_LINEAR_HIP_HPP

#include "../solver_cpu/sparse_linear.hpp"

#include <cstdint>
#include <span>
#include <string>

namespace structural::hip {

/// Source- and device-bound receipt for one no-fallback HIP PCG execution.
struct SparseLinearExecutionReceipt {
    std::int32_t device_id;
    std::string device_name;
    std::string architecture;
    std::int32_t runtime_version;
    std::int32_t driver_version;
    std::string compiler_version;
    std::string compiled_architectures;
    std::string kernel_source_sha256;
    std::string device_library_sha256;
    std::string reduction_profile;
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
    bool device_resident_iterations;
    std::uint64_t host_intermediate_state_transfer_count;
    std::uint64_t host_iteration_control_transfer_count;
};

struct SparseLinearHipExecution {
    solver_cpu::SparseLinearResult result;
    SparseLinearExecutionReceipt receipt;
};

/*
 * Solve one bounded canonical-CSR SPD problem with all PCG vectors, preconditioner state,
 * reductions and iteration control resident on the selected HIP device. Validation is shared
 * with the CPU reference source. Any HIP failure throws; no CPU solve or fallback branch exists.
 */
[[nodiscard]] SparseLinearHipExecution solve_sparse_spd_pcg_hip(
    solver_cpu::CsrMatrixView matrix,
    std::span<const double> right_hand_side,
    std::span<const double> initial_guess,
    const solver_cpu::SparseLinearConfig& config);

}  // namespace structural::hip

#endif
