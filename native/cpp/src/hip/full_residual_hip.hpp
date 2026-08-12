#ifndef STRUCTURAL_HIP_FULL_RESIDUAL_HIP_HPP
#define STRUCTURAL_HIP_FULL_RESIDUAL_HIP_HPP

#include "../solver_cpu/full_residual.hpp"

#include <cstdint>
#include <memory>
#include <string>

namespace structural::hip {

enum class FullResidualHipDeviceStatus : std::uint32_t {
    available = 0U,
    backend_unavailable = 1U,
    device_mismatch = 2U,
};

struct FullResidualHipBuildIdentity {
    std::int32_t device_id;
    std::string device_name;
    std::string architecture;
    std::int32_t runtime_version;
    std::int32_t driver_version;
    std::string compiler_version;
    std::string compiled_architectures;
    std::string kernel_source_sha256;
    std::string device_library_sha256;
};

/// Probe only the requested device. This never selects a different device or a CPU fallback.
[[nodiscard]] FullResidualHipDeviceStatus full_residual_hip_device_status(
    std::int32_t device_id) noexcept;

/// Resolve the source-, toolchain-, runtime-, and device-bound identity for a live device.
[[nodiscard]] FullResidualHipBuildIdentity full_residual_hip_build_identity(
    std::int32_t device_id);

/// Deep-copy a validated operator into one deterministic FP64 resident HIP context.
[[nodiscard]] std::unique_ptr<solver_cpu::FullResidualContext>
make_hip_full_residual_context(
    solver_cpu::FullResidualOperator operator_data,
    std::int32_t device_id);

}  // namespace structural::hip

#endif
