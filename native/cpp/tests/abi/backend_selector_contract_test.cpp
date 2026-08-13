#include "structural/abi_v1.h"

#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <thread>
#include <vector>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

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

struct Fixture {
    std::array<std::uint64_t, 12> frame_dofs {0U, 1U, 2U, 0U, 1U, 2U, 0U, 1U, 2U, 0U, 1U, 2U};
    std::array<double, 144> frame_stiffness {};
    std::array<std::uint64_t, 4> row_offsets {0U, 1U, 2U, 3U};
    std::array<std::uint64_t, 3> columns {0U, 1U, 2U};
    std::array<double, 3> shell_values {2.0, 3.0, 4.0};
    std::array<double, 3> spring_values {1.0, 1.0, 1.0};
    std::array<double, 3> external_force {1.0, 2.0, 3.0};
    std::array<std::uint64_t, 2> free_dofs {0U, 2U};

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
            3U,
            3U,
            3U,
            2U,
            {0U, 0U},
        };
    }
};

[[nodiscard]] sa_api_v1 load_main(const std::uint32_t version) {
    const sa_api_request_v1 request {
        version,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] bool selector_is_append_only_and_fail_closed() {
    CHECK(SA_API_V1_11_MIN_SIZE == offsetof(sa_api_v1, backend_get_api));
    CHECK(SA_API_V1_12_MIN_SIZE == offsetof(sa_api_v1, model_ir_linear_assembly_sizes));
    const auto prior = load_main(SA_ABI_V1_11);
    CHECK(prior.abi_version == SA_ABI_V1_11);
    CHECK(prior.backend_get_api == nullptr);
    CHECK((prior.capabilities & SA_CAPABILITY_BACKEND_SELECTOR) == 0U);

    const auto current = load_main(SA_ABI_V1_12);
    CHECK(current.abi_version == SA_ABI_V1_12);
    CHECK(current.backend_get_api != nullptr);
    CHECK((current.capabilities & SA_CAPABILITY_BACKEND_SELECTOR) != 0U);

    sa_backend_request_v1 hip_request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        SA_EXECUTION_BACKEND_HIP,
        0,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 backend {};
    backend.abi_version = SA_ABI_V1_12;
    backend.struct_size = static_cast<std::uint32_t>(sizeof(sa_backend_api_v1));
    std::array<std::byte, sizeof(backend)> before {};
    std::memset(&backend.execution_backend, 0xA5, sizeof(backend) - 8U);
    std::memcpy(before.data(), &backend, before.size());
    const auto hip_status = current.backend_get_api(&hip_request, &backend, nullptr);
    if (hip_status == SA_OK) {
        CHECK(backend.execution_backend == SA_EXECUTION_BACKEND_HIP);
        CHECK(backend.device_id == 0);
        CHECK(backend.full_residual_create != nullptr);
    } else {
        CHECK(hip_status == SA_ERR_BACKEND_UNAVAILABLE);
        CHECK(std::memcmp(before.data(), &backend, before.size()) == 0);
    }

    hip_request.device_id = -1;
    std::memcpy(before.data(), &backend, before.size());
    CHECK(current.backend_get_api(&hip_request, &backend, nullptr) == SA_ERR_DEVICE_MISMATCH);
    CHECK(std::memcmp(before.data(), &backend, before.size()) == 0);

    alignas(sa_backend_api_v1) std::array<std::byte, 96> aliased_storage {};
    auto* const aliased_request =
        reinterpret_cast<sa_backend_request_v1*>(aliased_storage.data());
    *aliased_request = {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        SA_EXECUTION_BACKEND_CPU,
        -1,
        0U,
        {0U, 0U},
    };
    auto* const aliased_backend =
        reinterpret_cast<sa_backend_api_v1*>(aliased_storage.data() + 16U);
    aliased_backend->abi_version = SA_ABI_V1_12;
    aliased_backend->struct_size = static_cast<std::uint32_t>(sizeof(sa_backend_api_v1));
    const auto aliased_before = aliased_storage;
    CHECK(current.backend_get_api(aliased_request, aliased_backend, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(aliased_storage == aliased_before);
    return true;
}

[[nodiscard]] bool cpu_context_is_deterministic_resident_and_lifetime_safe() {
    const auto main = load_main(SA_ABI_V1_12);
    sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        SA_EXECUTION_BACKEND_CPU,
        -1,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 backend {};
    backend.abi_version = SA_ABI_V1_12;
    backend.struct_size = static_cast<std::uint32_t>(sizeof(sa_backend_api_v1));
    CHECK(main.backend_get_api(&request, &backend, nullptr) == SA_OK);
    CHECK(backend.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(backend.device_id == -1);
    CHECK(backend.capabilities == SA_BACKEND_CAPABILITY_FULL_RESIDUAL);
    CHECK(backend.full_residual_create != nullptr);
    CHECK(backend.full_residual_evaluate != nullptr);
    CHECK(backend.full_residual_destroy != nullptr);

    Fixture fixture;
    auto descriptor = fixture.descriptor();
    sa_full_residual_context_v1* context = nullptr;
    sa_full_residual_status_v1 status {};
    status.abi_version = SA_ABI_V1_12;
    status.struct_size = static_cast<std::uint32_t>(sizeof(status));
    CHECK(backend.full_residual_create(&descriptor, &context, &status, nullptr) == SA_OK);
    CHECK(context != nullptr);
    CHECK(status.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(status.fallback_count == 0U);
    CHECK(status.frame_element_count == 1U);
    CHECK(status.order == 3U);
    CHECK((status.flags & SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT) == 0U);

    std::uint64_t name_size = 0U;
    CHECK(backend.full_residual_device_name_size(context, &name_size, nullptr) == SA_OK);
    CHECK(name_size == sizeof("deterministic-cpu-fp64"));
    std::array<char, 32> name {};
    CHECK(backend.full_residual_device_name_write(context, name.data(), name_size - 1U, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(backend.full_residual_device_name_write(context, name.data(), name.size(), nullptr)
          == SA_OK);
    CHECK(std::strcmp(name.data(), "deterministic-cpu-fp64") == 0);

    std::atomic_bool immutable_reads_ok {true};
    std::vector<std::thread> readers;
    for (std::size_t thread_index = 0U; thread_index < 8U; ++thread_index) {
        readers.emplace_back([&backend, context, &immutable_reads_ok]() {
            for (std::size_t iteration = 0U; iteration < 100U; ++iteration) {
                std::uint64_t local_size = 0U;
                std::array<char, 32> local_name {};
                if (backend.full_residual_device_name_size(context, &local_size, nullptr) != SA_OK
                    || local_size != sizeof("deterministic-cpu-fp64")
                    || backend.full_residual_device_name_write(
                           context, local_name.data(), local_name.size(), nullptr)
                        != SA_OK
                    || std::strcmp(local_name.data(), "deterministic-cpu-fp64") != 0) {
                    immutable_reads_ok.store(false);
                    return;
                }
            }
        });
    }
    for (auto& reader : readers) {
        reader.join();
    }
    CHECK(immutable_reads_ok.load());

    const std::array<double, 6> states {1.0, 2.0, 3.0, 4.0, 5.0, 6.0};
    std::array<double, 4> residual {-9.0, -9.0, -9.0, -9.0};
    const auto state_view = input(states.data(), states.size(), SA_ELEMENT_TYPE_F64);
    const auto residual_view = output(residual.data(), residual.size());
    const sa_full_residual_eval_config_v1 config {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_full_residual_eval_config_v1)),
        2U,
        3U,
        0U,
        {0U, 0U},
    };
    CHECK(backend.full_residual_evaluate(
              context, &config, &state_view, &residual_view, &status, nullptr)
          == SA_OK);
    const std::array<double, 4> expected {2.0, 12.0, 11.0, 27.0};
    CHECK(residual == expected);
    CHECK(status.batch_size == 2U);
    CHECK(status.repetitions == 3U);
    CHECK(status.fallback_count == 0U);
    CHECK(status.h2d_bytes == 0U && status.d2h_bytes == 0U);
    CHECK(status.output_abs_sum == 52.0);
    CHECK(status.output_max_abs == 27.0);
    CHECK((status.flags & SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED) == 0U);

    residual.fill(-1.0);
    CHECK(backend.full_residual_evaluate(
              context, &config, &state_view, &residual_view, &status, nullptr)
          == SA_OK);
    CHECK(residual == expected);
    CHECK((status.flags & SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED) != 0U);

    CHECK(backend.full_residual_destroy(context, nullptr) == SA_OK);
    CHECK(backend.full_residual_destroy(context, nullptr) == SA_ERR_INVALID_ARGUMENT);
    CHECK(backend.full_residual_device_name_size(context, &name_size, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    return true;
}

[[nodiscard]] bool create_rejects_invalid_operator_atomically() {
    const auto main = load_main(SA_ABI_V1_12);
    const sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        SA_EXECUTION_BACKEND_CPU,
        -1,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 backend {};
    backend.abi_version = SA_ABI_V1_12;
    backend.struct_size = static_cast<std::uint32_t>(sizeof(sa_backend_api_v1));
    CHECK(main.backend_get_api(&request, &backend, nullptr) == SA_OK);

    Fixture fixture;
    fixture.free_dofs[1] = 0U;
    auto descriptor = fixture.descriptor();
    auto* context = reinterpret_cast<sa_full_residual_context_v1*>(std::uintptr_t {0x1234U});
    sa_full_residual_status_v1 status {};
    status.abi_version = SA_ABI_V1_12;
    status.struct_size = static_cast<std::uint32_t>(sizeof(status));
    status.output_max_abs = 17.0;
    const auto before = status;
    CHECK(backend.full_residual_create(&descriptor, &context, &status, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(context == reinterpret_cast<sa_full_residual_context_v1*>(std::uintptr_t {0x1234U}));
    CHECK(std::memcmp(&status, &before, sizeof(status)) == 0);

    descriptor = fixture.descriptor();
    const auto descriptor_before = descriptor;
    CHECK(backend.full_residual_create(
              &descriptor,
              reinterpret_cast<sa_full_residual_context_v1**>(&descriptor),
              nullptr,
              nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&descriptor, &descriptor_before, sizeof(descriptor)) == 0);
    return true;
}

[[nodiscard]] bool evaluation_bounds_aliasing_and_device_outputs_fail_closed() {
    const auto main = load_main(SA_ABI_V1_12);
    const sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        SA_EXECUTION_BACKEND_CPU,
        -1,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 backend {};
    backend.abi_version = SA_ABI_V1_12;
    backend.struct_size = static_cast<std::uint32_t>(sizeof(sa_backend_api_v1));
    CHECK(main.backend_get_api(&request, &backend, nullptr) == SA_OK);

    Fixture fixture;
    auto descriptor = fixture.descriptor();
    sa_full_residual_context_v1* context = nullptr;
    CHECK(backend.full_residual_create(&descriptor, &context, nullptr, nullptr) == SA_OK);

    std::array<double, 3> states {1.0, 2.0, 3.0};
    const auto original_states = states;
    const auto state_view = input(states.data(), states.size(), SA_ELEMENT_TYPE_F64);
    const auto overlapping_output = output(states.data(), 2U);
    sa_full_residual_status_v1 status {};
    status.abi_version = SA_ABI_V1_12;
    status.struct_size = static_cast<std::uint32_t>(sizeof(status));
    status.output_abs_sum = 19.0;
    const auto status_before = status;
    sa_full_residual_eval_config_v1 config {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_full_residual_eval_config_v1)),
        1U,
        1U,
        0U,
        {0U, 0U},
    };
    CHECK(backend.full_residual_evaluate(
              context, &config, &state_view, &overlapping_output, &status, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(states == original_states);
    CHECK(std::memcmp(&status, &status_before, sizeof(status)) == 0);

    std::array<double, 2> residual {-7.0, -7.0};
    const auto residual_view = output(residual.data(), residual.size());
    config.repetitions = std::numeric_limits<std::uint32_t>::max();
    CHECK(backend.full_residual_evaluate(
              context, &config, &state_view, &residual_view, &status, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK((residual == std::array<double, 2> {-7.0, -7.0}));
    CHECK(std::memcmp(&status, &status_before, sizeof(status)) == 0);

    CHECK(backend.full_residual_device_name_size(
              context, reinterpret_cast<std::uint64_t*>(context), nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(backend.full_residual_device_name_write(
              context, reinterpret_cast<char*>(context), 64U, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(backend.full_residual_destroy(context, nullptr) == SA_OK);
    return true;
}

}  // namespace

int main() {
    const std::array tests {
        selector_is_append_only_and_fail_closed,
        cpu_context_is_deterministic_resident_and_lifetime_safe,
        create_rejects_invalid_operator_atomically,
        evaluation_bounds_aliasing_and_device_outputs_fail_closed,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
