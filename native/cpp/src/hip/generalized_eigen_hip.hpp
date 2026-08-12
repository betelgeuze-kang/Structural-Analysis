#ifndef STRUCTURAL_HIP_GENERALIZED_EIGEN_HIP_HPP
#define STRUCTURAL_HIP_GENERALIZED_EIGEN_HIP_HPP

#include "../solver_cpu/generalized_eigen.hpp"

#include <cstdint>
#include <span>
#include <string>

namespace structural::hip {

/// Source-, toolchain-, and device-bound receipt for one bounded generalized-eigen execution.
struct GeneralizedEigenExecutionReceipt {
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
    bool device_resident_eigensolve;
    bool device_result_recovery;
    std::uint64_t host_intermediate_state_transfer_count;
    std::uint64_t host_iteration_control_transfer_count;
};

struct ModalEigenHipExecution {
    solver_cpu::ModalEigenResult result;
    GeneralizedEigenExecutionReceipt receipt;
};

struct BucklingEigenHipExecution {
    solver_cpu::BucklingEigenResult result;
    GeneralizedEigenExecutionReceipt receipt;
};

/// Solve one bounded dense modal problem without a CPU solve or fallback path.
[[nodiscard]] ModalEigenHipExecution solve_dense_modal_modes_hip(
    solver_cpu::DenseSymmetricMatrixView stiffness,
    solver_cpu::DenseSymmetricMatrixView mass,
    std::span<const double> coordinate_recovery_scale,
    const solver_cpu::GeneralizedEigenConfig& config);

/// Solve one bounded dense linear-buckling problem without a CPU solve or fallback path.
[[nodiscard]] BucklingEigenHipExecution solve_dense_linear_buckling_hip(
    solver_cpu::DenseSymmetricMatrixView stiffness,
    solver_cpu::DenseSymmetricMatrixView geometric_stiffness_per_unit_load,
    std::span<const double> coordinate_recovery_scale,
    const solver_cpu::GeneralizedEigenConfig& config);

}  // namespace structural::hip

#endif
