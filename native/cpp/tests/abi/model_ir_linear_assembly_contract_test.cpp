#include "structural/abi_v1.h"

#include "model_ir_assembly_fixture.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
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

struct ErrorStorage final {
    std::array<char, 256> bytes {};
    sa_error_buffer_v1 descriptor {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        bytes.data(),
        bytes.size(),
        0U,
    };
};

[[nodiscard]] sa_api_v1 load_api(
    const std::uint32_t version,
    const std::uint32_t output_size = static_cast<std::uint32_t>(sizeof(sa_api_v1))) {
    const sa_api_request_v1 request {
        version,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = output_size;
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] sa_model_ir_linear_assembly_sizes_v1 empty_sizes() {
    return {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_sizes_v1)),
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        {0U, 0U},
    };
}

[[nodiscard]] sa_buffer_view_v1 input_view(const double* const data, const std::uint64_t length) {
    return {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        data,
        length,
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

template <typename Value>
[[nodiscard]] sa_mut_buffer_view_v1 output_view(
    std::vector<Value>& values,
    const std::uint32_t element_type) {
    return {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.empty() ? nullptr : values.data(),
        static_cast<std::uint64_t>(values.size()),
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

struct OutputStorage final {
    std::vector<std::uint32_t> active_dof_indices;
    std::vector<std::uint64_t> row_offsets;
    std::vector<std::uint32_t> column_indices;
    std::vector<double> tangent;
    std::vector<double> consistent_mass;
    std::vector<double> internal_force;
    std::vector<double> external_load;
    std::vector<double> equilibrium_residual;
    std::vector<double> jvp;
    std::vector<std::uint64_t> recovery_stable_indices;
    std::vector<std::uint32_t> recovery_element_types;
    std::vector<std::uint64_t> recovery_offsets;
    std::vector<double> recovery_values;
    std::vector<std::uint8_t> model_content_hash;
    std::vector<std::uint8_t> model_semantic_hash;
    std::vector<std::uint8_t> model_provenance_hash;

    explicit OutputStorage(
        const sa_model_ir_linear_assembly_sizes_v1& sizes,
        const bool sentinel = false)
        : active_dof_indices(sizes.active_dof_count, sentinel ? 0xA5A5A5A5U : 0U),
          row_offsets(sizes.row_offset_count, sentinel ? UINT64_C(0xA5A5A5A5A5A5A5A5) : 0U),
          column_indices(sizes.structural_entry_count, sentinel ? 0xA5A5A5A5U : 0U),
          tangent(sizes.structural_entry_count, sentinel ? -123.25 : 0.0),
          consistent_mass(sizes.structural_entry_count, sentinel ? -123.25 : 0.0),
          internal_force(sizes.active_dof_count, sentinel ? -123.25 : 0.0),
          external_load(sizes.active_dof_count, sentinel ? -123.25 : 0.0),
          equilibrium_residual(sizes.active_dof_count, sentinel ? -123.25 : 0.0),
          jvp(sizes.active_dof_count, sentinel ? -123.25 : 0.0),
          recovery_stable_indices(
              sizes.recovery_record_count,
              sentinel ? UINT64_C(0xA5A5A5A5A5A5A5A5) : 0U),
          recovery_element_types(sizes.recovery_record_count, sentinel ? 0xA5A5A5A5U : 0U),
          recovery_offsets(
              sizes.recovery_offset_count,
              sentinel ? UINT64_C(0xA5A5A5A5A5A5A5A5) : 0U),
          recovery_values(sizes.recovery_value_count, sentinel ? -123.25 : 0.0),
          model_content_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U),
          model_semantic_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U),
          model_provenance_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U) {}

    [[nodiscard]] sa_model_ir_linear_assembly_outputs_v1 descriptor() {
        return {
            SA_ABI_V1_13,
            static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_outputs_v1)),
            output_view(active_dof_indices, SA_ELEMENT_TYPE_U32),
            output_view(row_offsets, SA_ELEMENT_TYPE_U64),
            output_view(column_indices, SA_ELEMENT_TYPE_U32),
            output_view(tangent, SA_ELEMENT_TYPE_F64),
            output_view(consistent_mass, SA_ELEMENT_TYPE_F64),
            output_view(internal_force, SA_ELEMENT_TYPE_F64),
            output_view(external_load, SA_ELEMENT_TYPE_F64),
            output_view(equilibrium_residual, SA_ELEMENT_TYPE_F64),
            output_view(jvp, SA_ELEMENT_TYPE_F64),
            output_view(recovery_stable_indices, SA_ELEMENT_TYPE_U64),
            output_view(recovery_element_types, SA_ELEMENT_TYPE_U32),
            output_view(recovery_offsets, SA_ELEMENT_TYPE_U64),
            output_view(recovery_values, SA_ELEMENT_TYPE_F64),
            output_view(model_content_hash, SA_ELEMENT_TYPE_U8),
            output_view(model_semantic_hash, SA_ELEMENT_TYPE_U8),
            output_view(model_provenance_hash, SA_ELEMENT_TYPE_U8),
            {0U, 0U},
        };
    }

    [[nodiscard]] bool operator==(const OutputStorage&) const = default;
};

[[nodiscard]] sa_model_ir_linear_assembly_result_v1 empty_result() {
    return {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_result_v1)),
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        0U,
        {0U, 0U},
    };
}

[[nodiscard]] bool table_is_append_only() {
    const auto legacy = load_api(SA_ABI_V1_12, SA_API_V1_12_MIN_SIZE);
    CHECK(legacy.abi_version == SA_ABI_V1_12);
    CHECK(legacy.struct_size == sizeof(sa_api_v1));
    CHECK((legacy.capabilities & SA_CAPABILITY_BACKEND_SELECTOR) != 0U);
    CHECK((legacy.capabilities & SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU) == 0U);
    CHECK(legacy.model_ir_linear_assembly_sizes == nullptr);
    CHECK(legacy.model_ir_linear_assemble == nullptr);

    const auto current = load_api(SA_ABI_V1_13);
    CHECK(current.abi_version == SA_ABI_V1_13);
    CHECK((current.capabilities & SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU) != 0U);
    CHECK(current.model_ir_linear_assembly_sizes != nullptr);
    CHECK(current.model_ir_linear_assemble != nullptr);
    return true;
}

[[nodiscard]] bool successful_assembly_is_canonical_and_deterministic() {
    const auto api = load_api(SA_ABI_V1_13);
    structural::tests::ModelIrAssemblyFixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);

    auto sizes = empty_sizes();
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) == SA_OK);
    CHECK(sizes.global_dof_count == 18U);
    CHECK(sizes.active_dof_count == 7U);
    CHECK(sizes.row_offset_count == 8U);
    CHECK(sizes.structural_entry_count == 43U);
    CHECK(sizes.recovery_record_count == 2U);
    CHECK(sizes.recovery_offset_count == 3U);
    CHECK(sizes.recovery_value_count == 15U);
    CHECK(sizes.model_identity_length == 71U);

    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    const sa_model_ir_linear_assembly_config_v1 config {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_config_v1)),
        structural::tests::text("lp"),
        input_view(displacement.data(), displacement.size()),
        input_view(direction.data(), direction.size()),
        0U,
        {0U, 0U},
    };
    OutputStorage storage(sizes);
    auto outputs = storage.descriptor();
    auto result = empty_result();
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr) == SA_OK);
    CHECK(result.global_dof_count == sizes.global_dof_count);
    CHECK(result.active_dof_count == sizes.active_dof_count);
    CHECK(result.row_offset_count == sizes.row_offset_count);
    CHECK(result.structural_entry_count == sizes.structural_entry_count);
    CHECK(result.recovery_record_count == sizes.recovery_record_count);
    CHECK(result.recovery_value_count == sizes.recovery_value_count);
    CHECK(result.load_pattern_index == 0U);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(storage.active_dof_indices == std::vector<std::uint32_t>({6U, 7U, 8U, 9U, 10U, 11U, 13U}));
    CHECK(storage.row_offsets == std::vector<std::uint64_t>({0U, 7U, 14U, 21U, 27U, 33U, 39U, 43U}));
    CHECK(storage.external_load == std::vector<double>({10.0, -20.0, 0.0, 0.0, 0.0, 0.0, 30.0}));
    CHECK(storage.recovery_stable_indices == std::vector<std::uint64_t>({0U, 1U}));
    CHECK(storage.recovery_element_types == std::vector<std::uint32_t>({SA_ELEMENT_FRAME_3D, SA_ELEMENT_TRUSS_3D}));
    CHECK(storage.recovery_offsets == std::vector<std::uint64_t>({0U, 12U, 15U}));
    CHECK(std::string(storage.model_content_hash.begin(), storage.model_content_hash.end())
          == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
    CHECK(std::string(storage.model_semantic_hash.begin(), storage.model_semantic_hash.end())
          == "sha256:1111111111111111111111111111111111111111111111111111111111111111");
    CHECK(std::string(storage.model_provenance_hash.begin(), storage.model_provenance_hash.end())
          == "sha256:2222222222222222222222222222222222222222222222222222222222222222");
    for (std::size_t index = 0U; index < storage.internal_force.size(); ++index) {
        CHECK(storage.equilibrium_residual[index]
              == storage.internal_force[index] - storage.external_load[index]);
    }
    CHECK(std::all_of(storage.tangent.begin(), storage.tangent.end(), [](const auto value) {
        return std::isfinite(value);
    }));

    OutputStorage repeated(sizes);
    auto repeated_outputs = repeated.descriptor();
    auto repeated_result = empty_result();
    CHECK(api.model_ir_linear_assemble(
              handle, &config, &repeated_outputs, &repeated_result, nullptr)
          == SA_OK);
    CHECK(repeated == storage);
    CHECK(std::memcmp(&repeated_result, &result, sizeof(result)) == 0);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool bounded_direct_linear_combination_crosses_the_frozen_abi() {
    const auto api = load_api(SA_ABI_V1_13);
    structural::tests::ModelIrAssemblyFixture fixture;
    fixture.enable_three_pattern_linear_combination();
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);

    auto sizes = empty_sizes();
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) == SA_OK);
    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    const sa_model_ir_linear_assembly_config_v1 config {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_config_v1)),
        structural::tests::text("combo"),
        input_view(displacement.data(), displacement.size()),
        input_view(direction.data(), direction.size()),
        0U,
        {0U, 0U},
    };
    OutputStorage storage(sizes);
    auto outputs = storage.descriptor();
    auto result = empty_result();
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr) == SA_OK);
    CHECK(result.load_pattern_index == 0U);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(storage.external_load
          == std::vector<double>({12.0, -24.0, -4.0, 0.0, 0.0, 0.0, 40.0}));

    OutputStorage repeated(sizes);
    auto repeated_outputs = repeated.descriptor();
    auto repeated_result = empty_result();
    CHECK(api.model_ir_linear_assemble(
              handle, &config, &repeated_outputs, &repeated_result, nullptr)
          == SA_OK);
    CHECK(repeated == storage);
    CHECK(std::memcmp(&repeated_result, &result, sizeof(result)) == 0);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool failures_are_atomic_and_aliases_fail_closed() {
    const auto api = load_api(SA_ABI_V1_13);
    structural::tests::ModelIrAssemblyFixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    auto sizes = empty_sizes();
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) == SA_OK);
    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    auto config = sa_model_ir_linear_assembly_config_v1 {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_config_v1)),
        structural::tests::text("lp"),
        input_view(displacement.data(), displacement.size()),
        input_view(direction.data(), direction.size()),
        0U,
        {0U, 0U},
    };
    OutputStorage storage(sizes, true);
    const auto before = storage;
    auto outputs = storage.descriptor();
    --outputs.tangent.length;
    auto result = empty_result();
    result.global_dof_count = 0xA5A5U;
    const auto result_before = result;
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(storage == before);
    CHECK(std::memcmp(&result, &result_before, sizeof(result)) == 0);

    outputs = storage.descriptor();
    ++outputs.tangent.length;
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(storage == before);
    CHECK(std::memcmp(&result, &result_before, sizeof(result)) == 0);

    outputs = storage.descriptor();
    outputs.consistent_mass.data = outputs.tangent.data;
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(storage == before);
    CHECK(std::memcmp(&result, &result_before, sizeof(result)) == 0);

    outputs = storage.descriptor();
    config.load_pattern_id = structural::tests::text("*invalid");
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(storage == before);
    CHECK(std::memcmp(&result, &result_before, sizeof(result)) == 0);

    auto invalid_displacement = displacement;
    invalid_displacement[0] = 1.0;
    config.load_pattern_id = structural::tests::text("lp");
    config.displacement = input_view(invalid_displacement.data(), invalid_displacement.size());
    CHECK(api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(storage == before);
    CHECK(std::memcmp(&result, &result_before, sizeof(result)) == 0);

    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    auto stale_sizes = empty_sizes();
    const auto stale_before = stale_sizes;
    CHECK(api.model_ir_linear_assembly_sizes(handle, &stale_sizes, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&stale_sizes, &stale_before, sizeof(stale_sizes)) == 0);
    return true;
}

[[nodiscard]] bool immutable_calls_are_concurrent() {
    const auto api = load_api(SA_ABI_V1_13);
    structural::tests::ModelIrAssemblyFixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    auto sizes = empty_sizes();
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) == SA_OK);
    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    const sa_model_ir_linear_assembly_config_v1 config {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_config_v1)),
        structural::tests::text("lp"),
        input_view(displacement.data(), displacement.size()),
        input_view(direction.data(), direction.size()),
        0U,
        {0U, 0U},
    };
    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    for (std::size_t worker = 0U; worker < 8U; ++worker) {
        workers.emplace_back([&api, handle, &sizes, &config, &passed] {
            for (std::size_t iteration = 0U; iteration < 16U; ++iteration) {
                auto local_sizes = empty_sizes();
                OutputStorage storage(sizes);
                auto outputs = storage.descriptor();
                auto result = empty_result();
                if (api.model_ir_linear_assembly_sizes(handle, &local_sizes, nullptr) != SA_OK
                    || local_sizes.structural_entry_count != sizes.structural_entry_count
                    || api.model_ir_linear_assemble(
                           handle, &config, &outputs, &result, nullptr)
                        != SA_OK
                    || result.fallback_count != 0U) {
                    passed.store(false, std::memory_order_relaxed);
                }
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    CHECK(passed.load(std::memory_order_relaxed));
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool unsupported_graph_sizes_fail_atomically() {
    const auto api = load_api(SA_ABI_V1_13);
    structural::tests::ModelIrAssemblyFixture fixture;
    fixture.elements[0].offset_i_global_m[0] = 0.1;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    auto sizes = empty_sizes();
    sizes.global_dof_count = 0xA5A5U;
    const auto before = sizes;
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr)
          == SA_ERR_ANALYSIS_NOT_READY);
    CHECK(std::memcmp(&sizes, &before, sizeof(sizes)) == 0);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

}  // namespace

int main() {
    const std::array tests {
        table_is_append_only,
        successful_assembly_is_canonical_and_deterministic,
        bounded_direct_linear_combination_crosses_the_frozen_abi,
        failures_are_atomic_and_aliases_fail_closed,
        immutable_calls_are_concurrent,
        unsupported_graph_sizes_fail_atomically,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
