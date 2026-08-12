#include "dense_assembly.hpp"
#include "reference_elements.hpp"
#include "reference_elements_hip.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::exception&) {
        return;
    }
    expect(false, message);
}

[[nodiscard]] structural::elements::ElementOperatorResponse evaluate_cpu(
    const structural::hip::ReferenceElementInput& input) {
    return std::visit(
        [](const auto& value) {
            using Input = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<Input, structural::elements::Truss3dInput>) {
                return structural::elements::evaluate_truss3d(value);
            } else if constexpr (std::is_same_v<Input, structural::elements::Frame3dInput>) {
                return structural::elements::evaluate_frame3d(value);
            } else {
                return structural::elements::evaluate_shell3_membrane(value);
            }
        },
        input);
}

[[nodiscard]] double compare_vectors(
    const std::span<const double> cpu,
    const std::span<const double> device,
    const std::string_view label) {
    expect(cpu.size() == device.size(), "CPU/HIP vector length mismatch");
    auto max_error = 0.0;
    for (std::size_t index = 0U; index < cpu.size(); ++index) {
        const auto error = std::abs(cpu[index] - device[index]);
        const auto tolerance = 2.0E-12 + 2.0E-12 * std::abs(cpu[index]);
        if (!std::isfinite(device[index]) || error > tolerance) {
            std::cerr << label << " mismatch at " << index << ": cpu="
                      << std::setprecision(17) << cpu[index] << " hip=" << device[index]
                      << " error=" << error << " tolerance=" << tolerance << '\n';
            std::exit(EXIT_FAILURE);
        }
        max_error = std::max(max_error, error);
    }
    return max_error;
}

[[nodiscard]] bool same_response(
    const structural::elements::ElementOperatorResponse& left,
    const structural::elements::ElementOperatorResponse& right) {
    return left.kind == right.kind && left.dof_count == right.dof_count
        && left.tangent == right.tangent
        && left.consistent_mass == right.consistent_mass
        && left.residual == right.residual && left.jvp == right.jvp
        && left.recovery == right.recovery;
}

}  // namespace

int main() {
    const structural::materials::ElasticIsotropic material {200.0, 0.25, 1000.0};
    const std::array<double, 6> truss_displacement {0.0, 0.0, 0.0, 0.002, 0.0, 0.0};
    const std::array<double, 6> truss_direction {0.0, 0.0, 0.0, 1.0, 0.0, 0.0};
    const std::array<double, 12> frame_displacement {
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.001, 0.002, -0.003, 0.004, -0.005, 0.006,
    };
    const std::array<double, 12> frame_direction {
        1.0, 2.0, 3.0, 4.0, 5.0, 6.0,
        7.0, 8.0, 9.0, 10.0, 11.0, 12.0,
    };
    const std::array<double, 12> rotated_frame_displacement {
        0.001, -0.002, 0.003, -0.004, 0.005, -0.006,
        0.007, -0.008, 0.009, -0.010, 0.011, -0.012,
    };
    const std::array<double, 12> rotated_frame_direction {
        -6.0, 5.0, -4.0, 3.0, -2.0, 1.0,
        0.5, -1.5, 2.5, -3.5, 4.5, -5.5,
    };
    const std::array<double, 9> shell_displacement {
        0.0, 0.0, 0.0,
        0.002, 0.0, 0.0,
        0.0, 0.001, 0.0,
    };
    const std::array<double, 9> shell_direction {
        0.0, 0.0, 1.0,
        0.0, 0.0, 2.0,
        0.0, 0.0, 3.0,
    };
    const std::array<double, 9> rotated_shell_displacement {
        0.001, -0.002, 0.003,
        -0.004, 0.005, -0.006,
        0.007, -0.008, 0.009,
    };
    const std::array<double, 9> rotated_shell_direction {
        -1.0, 2.0, -3.0,
        4.0, -5.0, 6.0,
        -7.0, 8.0, -9.0,
    };

    const std::array<structural::hip::ReferenceElementInput, 5> inputs {
        structural::elements::Truss3dInput {
            {0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, material, 0.01,
            truss_displacement, truss_direction},
        structural::elements::Frame3dInput {
            {0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, material, 0.01,
            2.0E-5, 3.0E-5, 4.0E-5, 0.0, frame_displacement, frame_direction},
        structural::elements::Frame3dInput {
            {1.0, -2.0, 0.5}, {3.0, 1.0, 4.5}, material, 0.01,
            2.0E-5, 3.0E-5, 4.0E-5, 0.37,
            rotated_frame_displacement, rotated_frame_direction},
        structural::elements::Shell3MembraneInput {
            {{{0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, {0.0, 1.0, 0.0}}},
            material, 0.1, shell_displacement, shell_direction},
        structural::elements::Shell3MembraneInput {
            {{{1.0, -1.0, 0.5}, {3.0, 0.0, 2.5}, {0.0, 1.0, 3.5}}},
            material, 0.1, rotated_shell_displacement, rotated_shell_direction},
    };
    const std::array<std::uint32_t, 6> truss_dofs {0U, 1U, 2U, 3U, 4U, 5U};
    const std::array<std::uint32_t, 12> frame_dofs {
        3U, 4U, 5U, 6U, 7U, 8U, 9U, 10U, 11U, 12U, 13U, 14U};
    const std::array<std::uint32_t, 12> rotated_frame_dofs {
        12U, 13U, 14U, 15U, 16U, 17U, 18U, 19U, 20U, 21U, 22U, 23U};
    const std::array<std::uint32_t, 9> shell_dofs {
        22U, 23U, 24U, 25U, 26U, 27U, 28U, 29U, 30U};
    const std::array<std::uint32_t, 9> rotated_shell_dofs {
        29U, 30U, 31U, 32U, 33U, 34U, 35U, 36U, 37U};
    const std::array entries {
        structural::hip::ReferenceElementAssemblyEntry {50U, truss_dofs, inputs[0]},
        structural::hip::ReferenceElementAssemblyEntry {10U, frame_dofs, inputs[1]},
        structural::hip::ReferenceElementAssemblyEntry {40U, rotated_frame_dofs, inputs[2]},
        structural::hip::ReferenceElementAssemblyEntry {20U, shell_dofs, inputs[3]},
        structural::hip::ReferenceElementAssemblyEntry {30U, rotated_shell_dofs, inputs[4]},
    };

    std::vector<structural::elements::ElementOperatorResponse> cpu_responses;
    cpu_responses.reserve(inputs.size());
    for (const auto& input : inputs) {
        cpu_responses.push_back(evaluate_cpu(input));
    }
    std::vector<structural::assembly::DenseElementContribution> contributions;
    contributions.reserve(entries.size());
    for (std::size_t index = 0U; index < entries.size(); ++index) {
        const auto& response = cpu_responses[index];
        contributions.push_back({
            entries[index].stable_index,
            entries[index].global_dof_indices,
            response.tangent,
            response.consistent_mass,
            response.residual,
            response.jvp,
        });
    }
    const auto cpu_assembly =
        structural::assembly::assemble_dense_deterministic(38U, contributions);
    const auto device =
        structural::hip::evaluate_and_assemble_reference_elements(38U, entries);
    expect(device.element_responses.size() == cpu_responses.size(), "HIP response count");

    auto max_element_error = 0.0;
    for (std::size_t index = 0U; index < cpu_responses.size(); ++index) {
        const auto& cpu = cpu_responses[index];
        const auto& gpu = device.element_responses[index];
        expect(cpu.kind == gpu.kind && cpu.dof_count == gpu.dof_count, "CPU/HIP metadata");
        max_element_error = std::max(
            max_element_error,
            compare_vectors(cpu.tangent, gpu.tangent, "element tangent"));
        max_element_error = std::max(
            max_element_error,
            compare_vectors(cpu.consistent_mass, gpu.consistent_mass, "element mass"));
        max_element_error = std::max(
            max_element_error,
            compare_vectors(cpu.residual, gpu.residual, "element residual"));
        max_element_error = std::max(
            max_element_error,
            compare_vectors(cpu.jvp, gpu.jvp, "element JVP"));
        max_element_error = std::max(
            max_element_error,
            compare_vectors(cpu.recovery, gpu.recovery, "element recovery"));
    }
    auto max_assembly_error = compare_vectors(
        cpu_assembly.tangent, device.assembly.tangent, "assembly tangent");
    max_assembly_error = std::max(
        max_assembly_error,
        compare_vectors(
            cpu_assembly.consistent_mass,
            device.assembly.consistent_mass,
            "assembly mass"));
    max_assembly_error = std::max(
        max_assembly_error,
        compare_vectors(cpu_assembly.residual, device.assembly.residual, "assembly residual"));
    max_assembly_error = std::max(
        max_assembly_error,
        compare_vectors(cpu_assembly.jvp, device.assembly.jvp, "assembly JVP"));

    const auto repeated =
        structural::hip::evaluate_and_assemble_reference_elements(38U, entries);
    expect(repeated.element_responses.size() == device.element_responses.size(), "repeat count");
    for (std::size_t index = 0U; index < repeated.element_responses.size(); ++index) {
        expect(
            same_response(repeated.element_responses[index], device.element_responses[index]),
            "HIP element execution must be bitwise deterministic");
    }
    expect(repeated.assembly.tangent == device.assembly.tangent, "HIP tangent determinism");
    expect(
        repeated.assembly.consistent_mass == device.assembly.consistent_mass,
        "HIP mass determinism");
    expect(repeated.assembly.residual == device.assembly.residual, "HIP residual determinism");
    expect(repeated.assembly.jvp == device.assembly.jvp, "HIP JVP determinism");

    const auto& receipt = device.receipt;
    expect(receipt.device_id >= 0, "HIP device id");
    expect(!receipt.device_name.empty() && !receipt.architecture.empty(), "HIP device identity");
    expect(receipt.runtime_version > 0 && receipt.driver_version > 0, "ROCm versions");
    expect(!receipt.compiler_version.empty(), "HIP compiler identity");
    expect(
        receipt.compiled_architectures.find(receipt.architecture) != std::string::npos,
        "runtime device must match a compiled HIP architecture");
    expect(receipt.kernel_source_sha256.size() == 64U, "HIP source SHA-256");
    expect(receipt.device_library_sha256.size() == 64U, "HIP device-library SHA-256");
    expect(receipt.h2d_bytes > 0U && receipt.d2h_bytes > 0U, "HIP transfer bytes");
    expect(receipt.h2d_transfer_count == 1U, "one batched H2D transfer");
    expect(receipt.d2h_transfer_count == 5U, "five final D2H transfers");
    expect(receipt.synchronization_count == 1U, "one final synchronization");
    expect(receipt.kernel_launch_count == 2U, "element plus assembly kernels");
    expect(receipt.device_buffer_bytes > receipt.h2d_bytes, "resident device buffers");
    expect(receipt.vram_total_bytes > receipt.device_buffer_bytes, "VRAM capacity receipt");
    expect(
        receipt.vram_free_before_bytes <= receipt.vram_total_bytes
            && receipt.vram_free_after_alloc_bytes <= receipt.vram_total_bytes,
        "VRAM counters must be bounded by total memory");
    expect(receipt.fallback_count == 0U, "HIP fallback count must be zero");
    expect(receipt.fp64 && receipt.deterministic, "HIP FP64 deterministic policy");
    expect(receipt.device_resident_between_kernels, "element/operator residency");
    expect(receipt.host_intermediate_state_transfer_count == 0U, "no host intermediate state");

    auto duplicate = entries;
    duplicate[1].stable_index = duplicate[0].stable_index;
    expect_throws(
        [&duplicate] {
            static_cast<void>(
                structural::hip::evaluate_and_assemble_reference_elements(38U, duplicate));
        },
        "duplicate HIP stable index must fail before execution");

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-reference-elements-hip-receipt.v1\","
              << "\"backend\":\"amd_rocm_hip\",\"device_id\":" << receipt.device_id
              << ",\"device_name\":" << std::quoted(receipt.device_name)
              << ",\"architecture\":" << std::quoted(receipt.architecture)
              << ",\"runtime_version\":" << receipt.runtime_version
              << ",\"driver_version\":" << receipt.driver_version
              << ",\"compiler_version\":" << std::quoted(receipt.compiler_version)
              << ",\"compiled_architectures\":" << std::quoted(receipt.compiled_architectures)
              << ",\"kernel_source_sha256\":" << std::quoted(receipt.kernel_source_sha256)
              << ",\"device_library_sha256\":" << std::quoted(receipt.device_library_sha256)
              << ",\"reduction_profile\":" << std::quoted(receipt.reduction_profile)
              << ",\"element_count\":" << entries.size()
              << ",\"global_dof_count\":38"
              << ",\"max_element_absolute_error\":" << max_element_error
              << ",\"max_assembly_absolute_error\":" << max_assembly_error
              << ",\"h2d_bytes\":" << receipt.h2d_bytes
              << ",\"d2h_bytes\":" << receipt.d2h_bytes
              << ",\"h2d_transfer_count\":" << receipt.h2d_transfer_count
              << ",\"d2h_transfer_count\":" << receipt.d2h_transfer_count
              << ",\"synchronization_count\":" << receipt.synchronization_count
              << ",\"kernel_launch_count\":" << receipt.kernel_launch_count
              << ",\"device_buffer_bytes\":" << receipt.device_buffer_bytes
              << ",\"vram_total_bytes\":" << receipt.vram_total_bytes
              << ",\"vram_free_before_bytes\":" << receipt.vram_free_before_bytes
              << ",\"vram_free_after_alloc_bytes\":" << receipt.vram_free_after_alloc_bytes
              << ",\"fallback_count\":0,\"fp64\":true,\"deterministic\":true,"
              << "\"device_resident_between_kernels\":true,"
              << "\"host_intermediate_state_transfer_count\":0,\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
