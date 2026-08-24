#include "structural/abi_v1.h"

#include <array>
#include <atomic>
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

struct ErrorStorage {
    std::array<char, 128> bytes {};
    sa_error_buffer_v1 descriptor {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        bytes.data(),
        bytes.size(),
        0U,
    };
};

[[nodiscard]] sa_api_request_v1 request() {
    return {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
}

[[nodiscard]] sa_api_v1 output_table() {
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_0;
    api.struct_size = static_cast<std::uint32_t>(sizeof(sa_api_v1));
    return api;
}

[[nodiscard]] bool status_taxonomy_is_stable() {
    CHECK(SA_OK == 0);
    CHECK(SA_ERR_INVALID_ARGUMENT == 1000);
    CHECK(SA_ERR_ABI_VERSION_MISMATCH == 1001);
    CHECK(SA_ERR_STRUCT_SIZE == 1002);
    CHECK(SA_ERR_BUFFER_TOO_SMALL == 1003);
    CHECK(SA_ERR_SCHEMA_INVALID == 1100);
    CHECK(SA_ERR_SEMANTIC_INVALID == 1101);
    CHECK(SA_ERR_ANALYSIS_NOT_READY == 1102);
    CHECK(SA_ERR_UNSUPPORTED == 1200);
    CHECK(SA_ERR_STATE_CONFLICT == 1300);
    CHECK(SA_ERR_CHECKPOINT_MISMATCH == 1301);
    CHECK(SA_ERR_BACKEND_UNAVAILABLE == 1400);
    CHECK(SA_ERR_DEVICE_MISMATCH == 1401);
    CHECK(SA_ERR_FALLBACK_FORBIDDEN == 1402);
    CHECK(SA_ERR_CANCELLED == 1500);
    CHECK(SA_ERR_INTERNAL == 1900);
    return true;
}

[[nodiscard]] bool entry_table_supports_prefix_and_current_sizes() {
    auto current_request = request();
    auto api = output_table();
    ErrorStorage error;
    CHECK(sa_get_api_v1(&current_request, &api, &error.descriptor) == SA_OK);
    CHECK(api.abi_version == SA_ABI_V1_0);
    CHECK(api.struct_size == sizeof(sa_api_v1));
    CHECK(api.capabilities == SA_CAPABILITY_BUFFER_VALIDATION);
    CHECK(api.validate_buffer_view != nullptr);
    for (const auto* reserved : api.reserved) {
        CHECK(reserved == nullptr);
    }

    auto prefix_request = request();
    prefix_request.struct_size = SA_API_REQUEST_V1_MIN_SIZE;
    alignas(sa_api_v1) std::array<std::byte, SA_API_V1_MIN_SIZE> prefix_storage {};
    auto* prefix_api = reinterpret_cast<sa_api_v1*>(prefix_storage.data());
    prefix_api->abi_version = SA_ABI_V1_0;
    prefix_api->struct_size = SA_API_V1_MIN_SIZE;
    CHECK(sa_get_api_v1(&prefix_request, prefix_api, nullptr) == SA_OK);
    CHECK(prefix_api->abi_version == SA_ABI_V1_0);
    CHECK(prefix_api->capabilities == SA_CAPABILITY_BUFFER_VALIDATION);
    CHECK(prefix_api->validate_buffer_view != nullptr);
    return true;
}

[[nodiscard]] bool entry_failures_are_atomic() {
    auto invalid_request = request();
    invalid_request.abi_version = 0x0002'0000U;
    auto api = output_table();
    std::memset(api.reserved, 0xA5, sizeof(api.reserved));
    std::array<std::byte, sizeof(sa_api_v1)> before {};
    std::memcpy(before.data(), &api, before.size());
    ErrorStorage error;
    CHECK(sa_get_api_v1(&invalid_request, &api, &error.descriptor)
          == SA_ERR_ABI_VERSION_MISMATCH);
    CHECK(std::memcmp(before.data(), &api, before.size()) == 0);
    CHECK(error.descriptor.required > 1U);

    invalid_request = request();
    invalid_request.reserved[1] = 1U;
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_INVALID_ARGUMENT);

    invalid_request = request();
    invalid_request.struct_size = sizeof(sa_header_v1);
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_STRUCT_SIZE);

    invalid_request = request();
    invalid_request.struct_size = SA_API_REQUEST_V1_MIN_SIZE + 1U;
    api = output_table();
    CHECK(sa_get_api_v1(&invalid_request, &api, nullptr) == SA_ERR_STRUCT_SIZE);
    return true;
}

[[nodiscard]] bool caller_owned_error_buffers_are_bounded() {
    sa_error_buffer_v1 query {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        nullptr,
        0U,
        0U,
    };
    auto api = output_table();
    CHECK(sa_get_api_v1(nullptr, &api, &query) == SA_ERR_INVALID_ARGUMENT);
    CHECK(query.required > 1U);

    std::array<char, 4> tiny {'x', 'x', 'x', 'x'};
    sa_error_buffer_v1 truncated {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        tiny.data(),
        tiny.size(),
        0U,
    };
    CHECK(sa_get_api_v1(nullptr, &api, &truncated) == SA_ERR_INVALID_ARGUMENT);
    CHECK(truncated.required > tiny.size());
    CHECK(tiny.back() == '\0');

    sa_error_buffer_v1 malformed {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        tiny.data(),
        0U,
        77U,
    };
    CHECK(sa_get_api_v1(nullptr, &api, &malformed) == SA_ERR_INVALID_ARGUMENT);
    CHECK(malformed.required == 77U);
    return true;
}

[[nodiscard]] sa_buffer_view_v1 valid_view(const double* const values) {
    return {
        SA_ABI_V1_0,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values,
        2U,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] bool buffer_validation_is_fail_closed() {
    auto api = output_table();
    auto current_request = request();
    CHECK(sa_get_api_v1(&current_request, &api, nullptr) == SA_OK);
    const std::array<double, 2> values {1.0, 2.0};
    auto view = valid_view(values.data());
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_OK);

    view.data = nullptr;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.stride_bytes = sizeof(double) - 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.length = std::numeric_limits<std::uint64_t>::max();
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(reinterpret_cast<const double*>(
        std::numeric_limits<std::uintptr_t>::max() - 3U));
    view.length = 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.element_type = 999U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.flags = 1U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_INVALID_ARGUMENT);
    view = valid_view(values.data());
    view.memory_space = SA_MEMORY_SPACE_DEVICE;
    view.device_id = -1;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_DEVICE_MISMATCH);
    view.device_id = 0;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_ERR_BACKEND_UNAVAILABLE);

    view = valid_view(values.data());
    view.data = nullptr;
    view.length = 0U;
    CHECK(api.validate_buffer_view(&view, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool immutable_calls_are_concurrent() {
    auto api = output_table();
    auto current_request = request();
    CHECK(sa_get_api_v1(&current_request, &api, nullptr) == SA_OK);
    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    workers.reserve(8U);
    for (std::size_t worker = 0U; worker < 8U; ++worker) {
        workers.emplace_back([api, worker, &passed] {
            const std::array<double, 2> values {
                static_cast<double>(worker),
                static_cast<double>(worker + 1U),
            };
            const auto view = valid_view(values.data());
            for (std::size_t iteration = 0U; iteration < 512U; ++iteration) {
                ErrorStorage error;
                if (api.validate_buffer_view(&view, &error.descriptor) != SA_OK) {
                    passed.store(false, std::memory_order_relaxed);
                }
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    CHECK(passed.load(std::memory_order_relaxed));
    return true;
}

[[nodiscard]] bool frame3d_v1_2_table_and_lifetime_fail_closed() {
    auto current_request = request();
    current_request.abi_version = SA_ABI_V1_2;
    auto api = output_table();
    api.abi_version = SA_ABI_V1_2;
    ErrorStorage error;
    error.descriptor.abi_version = SA_ABI_V1_2;
    CHECK(sa_get_api_v1(&current_request, &api, &error.descriptor) == SA_OK);
    CHECK(api.capabilities
          == (SA_CAPABILITY_BUFFER_VALIDATION | SA_CAPABILITY_MODEL_IR_V2_TYPED
              | SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT | SA_CAPABILITY_LINEAR_FRAME3D_CPU));
    CHECK(api.linear_frame3d_model_compile != nullptr);
    CHECK(api.linear_frame3d_model_destroy != nullptr);
    CHECK(api.linear_frame3d_model_sizes != nullptr);
    CHECK(api.linear_frame3d_solve != nullptr);
    CHECK(api.linear_frame3d_solve_load_case == nullptr);

    const std::array nodes {
        sa_linear_frame3d_node_v1 {sizeof(sa_linear_frame3d_node_v1), 0U, 0.0, 0.0, 0.0},
        sa_linear_frame3d_node_v1 {sizeof(sa_linear_frame3d_node_v1), 0U, 2.0, 0.0, 0.0},
    };
    const std::array sections {sa_linear_frame3d_section_v1 {
        sizeof(sa_linear_frame3d_section_v1),
        0U,
        0.02,
        200'000'000.0,
        76'923'076.92307693,
        8.0e-5,
        5.0e-5,
        1.0e-5,
        0.015,
        0.014,
    }};
    const std::array members {sa_linear_frame3d_member_v1 {
        sizeof(sa_linear_frame3d_member_v1), 0U, 1U, 0U, {0U, 0U}, 0.0}};
    const std::array<std::uint32_t, 6> restrained {0U, 1U, 2U, 3U, 4U, 5U};
    const sa_linear_frame3d_model_input_v1 input {
        sizeof(sa_linear_frame3d_model_input_v1),
        1U,
        2U,
        0U,
        nodes.data(),
        nodes.size(),
        sections.data(),
        sections.size(),
        members.data(),
        members.size(),
        restrained.data(),
        restrained.size(),
    };
    auto legacy_input = input;
    legacy_input.abi_version_minor = 1U;
    auto* rejected_model = reinterpret_cast<sa_linear_frame3d_model_v1*>(std::uintptr_t {1U});
    CHECK(api.linear_frame3d_model_compile(
              &legacy_input, &rejected_model, &error.descriptor)
          == SA_ERR_ABI_VERSION_MISMATCH);
    CHECK(rejected_model == nullptr);
    sa_linear_frame3d_model_v1* model = nullptr;
    CHECK(api.linear_frame3d_model_compile(&input, &model, &error.descriptor) == SA_OK);
    CHECK(model != nullptr);

    std::uint64_t dof_count = 0U;
    std::uint64_t force_count = 0U;
    CHECK(api.linear_frame3d_model_sizes(
              model, &dof_count, &force_count, &error.descriptor)
          == SA_OK);
    CHECK(dof_count == 12U);
    CHECK(force_count == 12U);

    std::array<double, 12> loads {};
    loads[7] = -10.0;
    std::array<double, 12> displacements {};
    std::array<double, 12> reactions {};
    std::array<double, 12> member_end_forces {};
    sa_linear_frame3d_result_buffers_v1 results {
        sizeof(sa_linear_frame3d_result_buffers_v1),
        0U,
        displacements.data(),
        displacements.size(),
        reactions.data(),
        reactions.size(),
        member_end_forces.data(),
        member_end_forces.size(),
    };
    CHECK(api.linear_frame3d_solve(
              model, loads.data(), loads.size(), &results, &error.descriptor)
          == SA_OK);
    CHECK(displacements[7] < 0.0);
    CHECK(reactions[1] > 9.999999999 && reactions[1] < 10.000000001);

    std::atomic<bool> concurrent_passed {true};
    std::vector<std::thread> workers;
    workers.reserve(8U);
    for (std::size_t worker_index = 0U; worker_index < 8U; ++worker_index) {
        workers.emplace_back([api, model, loads, &concurrent_passed] {
            for (std::size_t iteration = 0U; iteration < 64U; ++iteration) {
                std::array<double, 12> worker_displacements {};
                std::array<double, 12> worker_reactions {};
                std::array<double, 12> worker_forces {};
                sa_linear_frame3d_result_buffers_v1 worker_results {
                    sizeof(sa_linear_frame3d_result_buffers_v1),
                    0U,
                    worker_displacements.data(),
                    worker_displacements.size(),
                    worker_reactions.data(),
                    worker_reactions.size(),
                    worker_forces.data(),
                    worker_forces.size(),
                };
                ErrorStorage worker_error;
                worker_error.descriptor.abi_version = SA_ABI_V1_2;
                if (api.linear_frame3d_solve(
                        model,
                        loads.data(),
                        loads.size(),
                        &worker_results,
                        &worker_error.descriptor)
                        != SA_OK
                    || !(worker_displacements[7] < 0.0)) {
                    concurrent_passed.store(false, std::memory_order_relaxed);
                }
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    CHECK(concurrent_passed.load(std::memory_order_relaxed));

    const auto* const stale = model;
    CHECK(api.linear_frame3d_model_destroy(model, &error.descriptor) == SA_OK);
    CHECK(api.linear_frame3d_model_sizes(
              stale, &dof_count, &force_count, &error.descriptor)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(api.linear_frame3d_model_destroy(
              const_cast<sa_linear_frame3d_model_v1*>(stale), &error.descriptor)
          == SA_ERR_INVALID_ARGUMENT);

    auto member_load_request = request();
    member_load_request.abi_version = SA_ABI_V1_3;
    auto member_load_api = output_table();
    member_load_api.abi_version = SA_ABI_V1_3;
    error.descriptor.abi_version = SA_ABI_V1_3;
    CHECK(sa_get_api_v1(&member_load_request, &member_load_api, &error.descriptor) == SA_OK);
    CHECK((member_load_api.capabilities
           & SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD)
          != 0U);
    CHECK(member_load_api.linear_frame3d_solve_load_case != nullptr);
    sa_linear_frame3d_model_v1* member_load_model = nullptr;
    CHECK(member_load_api.linear_frame3d_model_compile(
              &input, &member_load_model, &error.descriptor)
          == SA_OK);
    const std::array uniform_loads {sa_linear_frame3d_uniform_member_load_v1 {
        sizeof(sa_linear_frame3d_uniform_member_load_v1),
        0U,
        {0U, 0U},
        {0.0, -10.0, 0.0},
    }};
    const std::array<double, 12> zero_nodal_loads {};
    const sa_linear_frame3d_load_case_v1 load_case {
        sizeof(sa_linear_frame3d_load_case_v1),
        0U,
        zero_nodal_loads.data(),
        zero_nodal_loads.size(),
        uniform_loads.data(),
        uniform_loads.size(),
    };
    displacements.fill(0.0);
    reactions.fill(0.0);
    member_end_forces.fill(0.0);
    CHECK(member_load_api.linear_frame3d_solve_load_case(
              member_load_model, &load_case, &results, &error.descriptor)
          == SA_OK);
    CHECK(reactions[1] > 19.999999999 && reactions[1] < 20.000000001);
    CHECK(reactions[5] > 19.999999999 && reactions[5] < 20.000000001);
    CHECK(member_end_forces[7] > -1.0e-9 && member_end_forces[7] < 1.0e-9);
    CHECK(member_load_api.linear_frame3d_model_destroy(
              member_load_model, &error.descriptor)
          == SA_OK);

    auto release_request = request();
    release_request.abi_version = SA_ABI_V1_4;
    auto release_api = output_table();
    release_api.abi_version = SA_ABI_V1_4;
    error.descriptor.abi_version = SA_ABI_V1_4;
    CHECK(sa_get_api_v1(&release_request, &release_api, &error.descriptor) == SA_OK);
    CHECK((release_api.capabilities
           & SA_CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE)
          != 0U);
    auto released_members = members;
    SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_J(released_members[0]) = SA_FRAME3D_DOF_MASK_RZ;
    const std::array<std::uint32_t, 8> release_restraints {
        0U, 1U, 2U, 3U, 4U, 5U, 7U, 11U};
    auto release_input = input;
    release_input.abi_version_minor = 4U;
    release_input.members = released_members.data();
    release_input.restrained_dofs = release_restraints.data();
    release_input.restrained_dof_count = release_restraints.size();
    sa_linear_frame3d_model_v1* release_model = nullptr;
    CHECK(release_api.linear_frame3d_model_compile(
              &release_input, &release_model, &error.descriptor)
          == SA_OK);
    displacements.fill(0.0);
    reactions.fill(0.0);
    member_end_forces.fill(0.0);
    CHECK(release_api.linear_frame3d_solve_load_case(
              release_model, &load_case, &results, &error.descriptor)
          == SA_OK);
    CHECK(member_end_forces[11] > -1.0e-9 && member_end_forces[11] < 1.0e-9);
    CHECK(reactions[11] > -1.0e-9 && reactions[11] < 1.0e-9);
    CHECK(reactions[1] + reactions[7] > 19.999999999);
    CHECK(reactions[1] + reactions[7] < 20.000000001);
    CHECK(release_api.linear_frame3d_model_destroy(release_model, &error.descriptor) == SA_OK);

    auto compatibility_request = request();
    compatibility_request.abi_version = SA_ABI_V1_1;
    auto compatibility = output_table();
    compatibility.abi_version = SA_ABI_V1_1;
    CHECK(sa_get_api_v1(&compatibility_request, &compatibility, nullptr) == SA_OK);
    CHECK(compatibility.linear_frame3d_model_compile == nullptr);
    CHECK(compatibility.linear_frame3d_solve == nullptr);
    CHECK(compatibility.linear_frame3d_solve_load_case == nullptr);
    CHECK((compatibility.capabilities & SA_CAPABILITY_LINEAR_FRAME3D_CPU) == 0U);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        status_taxonomy_is_stable,
        entry_table_supports_prefix_and_current_sizes,
        entry_failures_are_atomic,
        caller_owned_error_buffers_are_bounded,
        buffer_validation_is_fail_closed,
        immutable_calls_are_concurrent,
        frame3d_v1_2_table_and_lifetime_fail_closed,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
