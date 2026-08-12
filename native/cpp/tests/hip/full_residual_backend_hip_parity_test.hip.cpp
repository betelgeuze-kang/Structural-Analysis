#include "full_residual_hip.hpp"
#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <string>
#include <string_view>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

template <typename Value>
[[nodiscard]] sa_buffer_view_v1 input(
    const Value* const data,
    const std::size_t length,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        length == 0U ? nullptr : data,
        length,
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_mut_buffer_view_v1 output(double* const data, const std::size_t length) {
    return {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        data,
        length,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_full_residual_status_v1 status_output() {
    sa_full_residual_status_v1 status {};
    status.abi_version = SA_ABI_V1_12;
    status.struct_size = static_cast<std::uint32_t>(sizeof(status));
    return status;
}

[[nodiscard]] sa_api_v1 main_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_12;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    expect(sa_get_api_v1(&request, &api, nullptr) == SA_OK, "load ABI v1.12");
    expect(api.backend_get_api != nullptr, "backend selector slot");
    return api;
}

[[nodiscard]] sa_backend_api_v1 backend(
    const sa_api_v1& main,
    const std::uint32_t execution_backend,
    const std::int32_t device_id) {
    const sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        execution_backend,
        device_id,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 selected {};
    selected.abi_version = SA_ABI_V1_12;
    selected.struct_size = static_cast<std::uint32_t>(sizeof(selected));
    expect(main.backend_get_api(&request, &selected, nullptr) == SA_OK, "select backend");
    expect(selected.execution_backend == execution_backend, "selected backend identity");
    expect(selected.device_id == device_id, "selected device identity");
    return selected;
}

struct Fixture {
    static constexpr std::size_t kOrder = 6U;
    static constexpr std::size_t kBatchSize = 3U;
    std::array<std::uint64_t, 12> frame_dofs {0U, 1U, 2U, 3U, 4U, 5U, 0U, 1U, 2U, 3U, 4U, 5U};
    std::array<double, 144> frame_stiffness {};
    std::array<std::uint64_t, 7> row_offsets {0U, 1U, 2U, 3U, 4U, 5U, 6U};
    std::array<std::uint64_t, 6> columns {0U, 1U, 2U, 3U, 4U, 5U};
    std::array<double, 6> shell_values {2.0, 2.5, 3.0, 3.5, 4.0, 4.5};
    std::array<double, 6> spring_values {0.5, 0.75, 1.0, 1.25, 1.5, 1.75};
    std::array<double, 6> external_force {1.0, -2.0, 3.0, -4.0, 5.0, -6.0};
    std::array<std::uint64_t, 6> free_dofs {5U, 3U, 1U, 0U, 2U, 4U};
    std::array<double, kOrder * kBatchSize> states {
        0.1, -0.2, 0.3, -0.4, 0.5, -0.6,
        1.25, -2.5, 3.75, -4.0, 5.5, -6.25,
        -0.75, 0.625, -0.5, 0.375, -0.25, 0.125,
    };

    Fixture() {
        for (std::size_t row = 0U; row < 12U; ++row) {
            for (std::size_t column = 0U; column < 12U; ++column) {
                const auto sign = (row + column) % 2U == 0U ? 1.0 : -1.0;
                frame_stiffness[row * 12U + column] =
                    sign * static_cast<double>((row + 1U) * (column + 2U)) / 1024.0;
            }
        }
    }

    [[nodiscard]] sa_full_residual_operator_v1 descriptor() const {
        return {
            SA_ABI_V1_12,
            static_cast<std::uint32_t>(sizeof(sa_full_residual_operator_v1)),
            input(frame_dofs.data(), frame_dofs.size(), SA_ELEMENT_TYPE_U64),
            input(frame_stiffness.data(), frame_stiffness.size(), SA_ELEMENT_TYPE_F64),
            input(row_offsets.data(), row_offsets.size(), SA_ELEMENT_TYPE_U64),
            input(columns.data(), columns.size(), SA_ELEMENT_TYPE_U64),
            input(shell_values.data(), shell_values.size(), SA_ELEMENT_TYPE_F64),
            input(row_offsets.data(), row_offsets.size(), SA_ELEMENT_TYPE_U64),
            input(columns.data(), columns.size(), SA_ELEMENT_TYPE_U64),
            input(spring_values.data(), spring_values.size(), SA_ELEMENT_TYPE_F64),
            input(external_force.data(), external_force.size(), SA_ELEMENT_TYPE_F64),
            input(free_dofs.data(), free_dofs.size(), SA_ELEMENT_TYPE_U64),
            1U,
            kOrder,
            columns.size(),
            columns.size(),
            free_dofs.size(),
            {0U, 0U},
        };
    }
};

struct Context {
    sa_backend_api_v1 api {};
    sa_full_residual_context_v1* raw {nullptr};
    sa_full_residual_status_v1 creation {};
};

[[nodiscard]] Context create_context(
    const sa_backend_api_v1& api,
    const sa_full_residual_operator_v1& descriptor) {
    Context context {api, nullptr, status_output()};
    expect(
        api.full_residual_create(&descriptor, &context.raw, &context.creation, nullptr) == SA_OK,
        "create full-residual context");
    expect(context.raw != nullptr, "non-null full-residual context");
    expect(context.creation.fallback_count == 0U, "create fallback count");
    return context;
}

[[nodiscard]] std::array<double, Fixture::kOrder * Fixture::kBatchSize> evaluate(
    Context& context,
    const Fixture& fixture,
    sa_full_residual_status_v1& status) {
    std::array<double, Fixture::kOrder * Fixture::kBatchSize> residual {};
    const auto states = input(fixture.states.data(), fixture.states.size(), SA_ELEMENT_TYPE_F64);
    const auto residual_output = output(residual.data(), residual.size());
    const sa_full_residual_eval_config_v1 config {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_full_residual_eval_config_v1)),
        Fixture::kBatchSize,
        4U,
        0U,
        {0U, 0U},
    };
    status = status_output();
    expect(
        context.api.full_residual_evaluate(
            context.raw, &config, &states, &residual_output, &status, nullptr)
            == SA_OK,
        "evaluate full-residual context");
    return residual;
}

}  // namespace

int main() {
    const auto main = main_api();
    const auto cpu_api = backend(main, SA_EXECUTION_BACKEND_CPU, -1);
    const auto hip_api = backend(main, SA_EXECUTION_BACKEND_HIP, 0);
    Fixture fixture;
    const auto descriptor = fixture.descriptor();
    auto cpu = create_context(cpu_api, descriptor);
    auto hip = create_context(hip_api, descriptor);
    expect(
        hip.creation.flags & SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT,
        "HIP operator is device resident");
    expect(hip.creation.h2d_transfer_count == 10U, "HIP operator upload count");
    expect(hip.creation.h2d_bytes > 0U, "HIP operator upload bytes");
    expect(hip.creation.synchronization_count == 1U, "HIP operator upload synchronization");
    expect(hip.creation.device_buffer_bytes > 0U, "HIP operator device buffers");
    expect(hip.creation.vram_total_bytes > hip.creation.device_buffer_bytes, "HIP VRAM total");

    sa_full_residual_status_v1 cpu_status {};
    sa_full_residual_status_v1 hip_first_status {};
    sa_full_residual_status_v1 hip_second_status {};
    const auto cpu_residual = evaluate(cpu, fixture, cpu_status);
    const auto hip_first = evaluate(hip, fixture, hip_first_status);
    const auto hip_second = evaluate(hip, fixture, hip_second_status);
    double maximum_absolute_error = 0.0;
    for (std::size_t index = 0U; index < cpu_residual.size(); ++index) {
        maximum_absolute_error = std::max(
            maximum_absolute_error, std::abs(cpu_residual[index] - hip_first[index]));
    }
    expect(maximum_absolute_error <= 2.0e-12, "CPU/HIP full-residual parity");
    expect(
        std::memcmp(hip_first.data(), hip_second.data(), sizeof(hip_first)) == 0,
        "HIP full-residual repeat is bitwise deterministic");
    expect(hip_first_status.execution_backend == SA_EXECUTION_BACKEND_HIP, "HIP status backend");
    expect(hip_first_status.fallback_count == 0U, "HIP evaluate fallback count");
    expect(
        (hip_first_status.flags & SA_FULL_RESIDUAL_FP64) != 0U
            && (hip_first_status.flags & SA_FULL_RESIDUAL_DETERMINISTIC) != 0U,
        "HIP deterministic FP64 status flags");
    expect(
        (hip_first_status.flags & SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED) == 0U,
        "first HIP eval allocates buffers");
    expect(
        (hip_second_status.flags & SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED) != 0U,
        "second HIP eval reuses buffers");
    expect(hip_first_status.h2d_transfer_count == 1U, "only states transfer to device");
    expect(hip_first_status.d2h_transfer_count == 1U, "only residual returns to host");
    expect(hip_first_status.synchronization_count == 1U, "one final HIP synchronization");
    expect(hip_first_status.kernel_launch_count == 4U, "one launch per requested repetition");
    expect(hip_first_status.h2d_bytes == fixture.states.size() * sizeof(double), "state bytes");
    expect(hip_first_status.d2h_bytes == hip_first.size() * sizeof(double), "residual bytes");
    expect(hip_first_status.device_buffer_bytes >= hip.creation.device_buffer_bytes, "resident bytes");
    expect(
        hip_first_status.vram_free_after_bytes <= hip_first_status.vram_total_bytes,
        "HIP post-eval VRAM counter");

    std::uint64_t device_name_size = 0U;
    expect(
        hip.api.full_residual_device_name_size(hip.raw, &device_name_size, nullptr) == SA_OK,
        "HIP device-name size");
    std::string device_name(static_cast<std::size_t>(device_name_size), '\0');
    expect(
        hip.api.full_residual_device_name_write(
            hip.raw, device_name.data(), device_name_size, nullptr)
            == SA_OK,
        "HIP device-name write");
    device_name.pop_back();
    const auto identity = structural::hip::full_residual_hip_build_identity(0);
    expect(device_name == identity.device_name, "ABI and HIP identity device name");
    expect(identity.runtime_version > 0 && identity.driver_version > 0, "ROCm identity versions");
    expect(identity.kernel_source_sha256.size() == 64U, "kernel source SHA-256");
    expect(identity.device_library_sha256.size() == 64U, "device-library SHA-256");
    expect(
        identity.compiled_architectures.find(identity.architecture.substr(0U, 7U))
            != std::string::npos,
        "runtime architecture is compiled");

    expect(cpu.api.full_residual_destroy(cpu.raw, nullptr) == SA_OK, "destroy CPU context");
    expect(hip.api.full_residual_destroy(hip.raw, nullptr) == SA_OK, "destroy HIP context");

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-full-residual-backend-hip-receipt.v1\","
              << "\"backend\":\"amd_rocm_hip\",\"device_id\":" << identity.device_id
              << ",\"device_name\":" << std::quoted(identity.device_name)
              << ",\"architecture\":" << std::quoted(identity.architecture)
              << ",\"runtime_version\":" << identity.runtime_version
              << ",\"driver_version\":" << identity.driver_version
              << ",\"compiler_version\":" << std::quoted(identity.compiler_version)
              << ",\"compiled_architectures\":" << std::quoted(identity.compiled_architectures)
              << ",\"kernel_source_sha256\":" << std::quoted(identity.kernel_source_sha256)
              << ",\"device_library_sha256\":" << std::quoted(identity.device_library_sha256)
              << ",\"max_residual_absolute_error\":" << maximum_absolute_error
              << ",\"operator_h2d_bytes\":" << hip.creation.h2d_bytes
              << ",\"eval_h2d_bytes\":" << hip_first_status.h2d_bytes
              << ",\"eval_d2h_bytes\":" << hip_first_status.d2h_bytes
              << ",\"operator_h2d_transfer_count\":10"
              << ",\"eval_h2d_transfer_count\":1,\"eval_d2h_transfer_count\":1"
              << ",\"operator_synchronization_count\":1"
              << ",\"eval_synchronization_count\":1,\"kernel_launch_count\":4"
              << ",\"device_buffer_bytes\":" << hip_first_status.device_buffer_bytes
              << ",\"vram_total_bytes\":" << hip_first_status.vram_total_bytes
              << ",\"vram_free_before_bytes\":" << hip.creation.vram_free_before_bytes
              << ",\"vram_free_after_bytes\":" << hip_first_status.vram_free_after_bytes
              << ",\"fallback_count\":0,\"fp64\":true,\"deterministic\":true"
              << ",\"operator_device_resident\":true,\"eval_buffers_reused\":true"
              << ",\"cpu_hip_parity\":true,\"hip_repeat_bitwise\":true"
              << ",\"single_entry_symbol\":\"sa_get_api_v1\",\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
