#ifndef STRUCTURAL_HIP_REFERENCE_ELEMENTS_HIP_HPP
#define STRUCTURAL_HIP_REFERENCE_ELEMENTS_HIP_HPP

#include "../assembly/dense_assembly.hpp"
#include "../elements/reference_elements.hpp"

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <variant>
#include <vector>

namespace structural::hip {

using ReferenceElementInput = std::variant<
    elements::Truss3dInput,
    elements::Frame3dInput,
    elements::Shell3MembraneInput>;

struct ReferenceElementAssemblyEntry {
    std::uint64_t stable_index;
    std::span<const std::uint32_t> global_dof_indices;
    ReferenceElementInput element;
};

struct ExecutionReceipt {
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
    bool device_resident_between_kernels;
    std::uint64_t host_intermediate_state_transfer_count;
};

struct ReferenceElementAssemblyExecution {
    std::vector<elements::ElementOperatorResponse> element_responses;
    assembly::DenseAssemblyResult assembly;
    ExecutionReceipt receipt;
};

/*
 * Evaluate a bounded batch and assemble it without copying element operator state back to the
 * host between the element and assembly kernels. Inputs and final evidence are caller-owned C++
 * values; any HIP failure throws and there is no CPU fallback path.
 */
[[nodiscard]] ReferenceElementAssemblyExecution evaluate_and_assemble_reference_elements(
    std::size_t global_dof_count,
    std::span<const ReferenceElementAssemblyEntry> entries);

}  // namespace structural::hip

#endif
