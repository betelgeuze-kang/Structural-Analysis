#include "structural/abi_v1.h"

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
#include <type_traits>

namespace {

[[noreturn]] void fail(const std::string_view operation, const char* const detail = "") {
    std::cerr << operation;
    if (detail[0] != '\0') {
        std::cerr << ": " << detail;
    }
    std::cerr << '\n';
    std::exit(EXIT_FAILURE);
}

void require(const bool condition, const std::string_view operation) {
    if (!condition) {
        fail(operation);
    }
}

struct ErrorBuffer {
    std::array<char, 512> bytes {};
    sa_error_buffer_v1 view {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        bytes.data(),
        bytes.size(),
        0U,
    };
};

void require_ok(
    const sa_status_code_v1 status,
    const std::string_view operation,
    const ErrorBuffer& error) {
    if (status != SA_OK) {
        fail(operation, error.bytes.data());
    }
}

template <typename Value>
[[nodiscard]] sa_buffer_view_v1 input(const Value* const data, const std::size_t length) {
    const auto type = std::is_same_v<Value, double> ? SA_ELEMENT_TYPE_F64 : SA_ELEMENT_TYPE_U64;
    return {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        data,
        length,
        sizeof(Value),
        static_cast<std::uint32_t>(type),
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

struct Fixture {
    std::array<std::uint64_t, 12> frame_dofs {};
    std::array<double, 144> frame_stiffness {};
    std::array<std::uint64_t, 2> row_offsets {0U, 1U};
    std::array<std::uint64_t, 1> columns {0U};
    std::array<double, 1> shell_values {2.0};
    std::array<double, 1> spring_values {3.0};
    std::array<double, 1> external_force {1.0};
    std::array<std::uint64_t, 1> free_dofs {0U};
    std::array<double, 2> states {4.0, -2.0};

    [[nodiscard]] sa_full_residual_operator_v1 descriptor() const {
        return {
            SA_ABI_V1_12,
            static_cast<std::uint32_t>(sizeof(sa_full_residual_operator_v1)),
            input(frame_dofs.data(), frame_dofs.size()),
            input(frame_stiffness.data(), frame_stiffness.size()),
            input(row_offsets.data(), row_offsets.size()),
            input(columns.data(), columns.size()),
            input(shell_values.data(), shell_values.size()),
            input(row_offsets.data(), row_offsets.size()),
            input(columns.data(), columns.size()),
            input(spring_values.data(), spring_values.size()),
            input(external_force.data(), external_force.size()),
            input(free_dofs.data(), free_dofs.size()),
            1U,
            1U,
            1U,
            1U,
            1U,
            {0U, 0U},
        };
    }
};

struct Evaluation {
    std::array<double, 2> first {};
    std::array<double, 2> second {};
    sa_full_residual_status_v1 creation {};
    sa_full_residual_status_v1 status {};
    std::string device_name;
};

[[nodiscard]] sa_api_v1 load_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_12;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    ErrorBuffer error;
    require_ok(sa_get_api_v1(&request, &api, &error.view), "load product API", error);
    require(api.backend_get_api != nullptr, "backend selector is absent");
    return api;
}

[[nodiscard]] sa_backend_api_v1 select_backend(
    const sa_api_v1& main_api,
    const std::uint32_t backend,
    const std::int32_t device_id) {
    const sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        backend,
        device_id,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 selected {};
    selected.abi_version = SA_ABI_V1_12;
    selected.struct_size = static_cast<std::uint32_t>(sizeof(selected));
    ErrorBuffer error;
    require_ok(
        main_api.backend_get_api(&request, &selected, &error.view),
        "select product backend",
        error);
    require(selected.execution_backend == backend, "selected backend identity drifted");
    require(selected.device_id == device_id, "selected device identity drifted");
    return selected;
}

[[nodiscard]] Evaluation evaluate(
    const sa_backend_api_v1& api,
    const Fixture& fixture) {
    auto creation = status_output();
    auto descriptor = fixture.descriptor();
    sa_full_residual_context_v1* context = nullptr;
    ErrorBuffer error;
    require_ok(
        api.full_residual_create(&descriptor, &context, &creation, &error.view),
        "create package backend context",
        error);
    require(context != nullptr, "package backend returned a null context");

    std::uint64_t device_name_size = 0U;
    require_ok(
        api.full_residual_device_name_size(context, &device_name_size, &error.view),
        "query package backend device name",
        error);
    require(device_name_size > 1U && device_name_size <= 4096U, "device name size is invalid");
    std::string device_name(static_cast<std::size_t>(device_name_size), '\0');
    require_ok(
        api.full_residual_device_name_write(
            context, device_name.data(), device_name_size, &error.view),
        "read package backend device name",
        error);
    device_name.pop_back();

    const sa_full_residual_eval_config_v1 config {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_full_residual_eval_config_v1)),
        2U,
        4U,
        0U,
        {0U, 0U},
    };
    const auto states = input(fixture.states.data(), fixture.states.size());
    Evaluation evaluation;
    evaluation.creation = creation;
    evaluation.device_name = device_name;
    for (auto* residual : {&evaluation.first, &evaluation.second}) {
        auto residual_view = output(residual->data(), residual->size());
        auto status = status_output();
        require_ok(
            api.full_residual_evaluate(
                context, &config, &states, &residual_view, &status, &error.view),
            "evaluate package backend",
            error);
        evaluation.status = status;
    }
    require_ok(
        api.full_residual_destroy(context, &error.view), "destroy package backend context", error);
    require(evaluation.first == evaluation.second, "package backend repeat is not bitwise stable");
    require(evaluation.first[0] == 19.0 && evaluation.first[1] == -11.0, "residual drifted");
    require(evaluation.status.fallback_count == 0U, "package backend used fallback");
    require(
        (evaluation.status.flags & SA_FULL_RESIDUAL_FP64) != 0U,
        "package backend did not declare FP64");
    require(
        (evaluation.status.flags & SA_FULL_RESIDUAL_DETERMINISTIC) != 0U,
        "package backend did not declare deterministic execution");
    return evaluation;
}

}  // namespace

int main(const int argc, const char* const* const argv) {
    if (argc != 2 || (std::strcmp(argv[1], "cpu") != 0 && std::strcmp(argv[1], "hip") != 0)) {
        fail("usage: structural_native_backend_package_consumer cpu|hip");
    }
    const bool run_hip = std::strcmp(argv[1], "hip") == 0;
    const auto main_api = load_api();
    const Fixture fixture;
    const auto cpu = evaluate(select_backend(main_api, SA_EXECUTION_BACKEND_CPU, -1), fixture);
    const auto selected = run_hip
        ? evaluate(select_backend(main_api, SA_EXECUTION_BACKEND_HIP, 0), fixture)
        : cpu;
    require(cpu.first == selected.first, "installed CPU/HIP results differ");
    if (run_hip) {
        require(
            (selected.creation.flags & SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT) != 0U,
            "installed HIP operator is not device resident");
        require(selected.creation.h2d_transfer_count == 10U, "installed HIP upload count drifted");
        require(selected.status.h2d_transfer_count == 1U, "installed HIP state upload count drifted");
        require(selected.status.d2h_transfer_count == 1U, "installed HIP result download count drifted");
        require(selected.status.synchronization_count == 1U, "installed HIP sync count drifted");
        require(selected.status.kernel_launch_count == 4U, "installed HIP launch count drifted");
        require(selected.status.device_buffer_bytes > 0U, "installed HIP VRAM metric is empty");
    }
    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"structural-native-installed-backend.v1\","
              << "\"backend_profile\":\"" << (run_hip ? "rocm" : "cpu_only") << "\","
              << "\"device_name\":" << std::quoted(selected.device_name) << ','
              << "\"cpu_backend\":" << cpu.status.execution_backend << ','
              << "\"execution_backend\":" << selected.status.execution_backend << ','
              << "\"device_id\":" << selected.status.device_id << ','
              << "\"cpu_backend_parity\":true,\"repeat_bitwise\":true,"
              << "\"fp64\":true,\"deterministic\":true,\"fallback_count\":0,"
              << "\"operator_device_resident\":"
              << (run_hip ? "true" : "false") << ','
              << "\"h2d_bytes\":" << selected.status.h2d_bytes << ','
              << "\"d2h_bytes\":" << selected.status.d2h_bytes << ','
              << "\"synchronization_count\":" << selected.status.synchronization_count << ','
              << "\"kernel_launch_count\":" << selected.status.kernel_launch_count << ','
              << "\"device_buffer_bytes\":" << selected.status.device_buffer_bytes << "}\n";
    return EXIT_SUCCESS;
}
