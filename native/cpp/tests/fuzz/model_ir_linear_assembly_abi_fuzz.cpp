#include "structural/abi_v1.h"

#include "model_ir_assembly_fixture.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>

namespace {

[[noreturn]] void fail() {
    std::abort();
}

[[nodiscard]] sa_api_v1 load_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_13;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK
        || api.model_ir_linear_assembly_sizes == nullptr
        || api.model_ir_linear_assemble == nullptr) {
        fail();
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

[[nodiscard]] sa_model_ir_linear_assembly_result_v1 empty_result() {
    return {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_result_v1)),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        UINT64_C(0xA5A5A5A5A5A5A5A5),
        0xA5A5A5A5U,
        0xA5A5A5A5U,
        {0U, 0U},
    };
}

[[nodiscard]] sa_buffer_view_v1 input_view(
    const double* const data,
    const std::uint64_t length) {
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

    explicit OutputStorage(const sa_model_ir_linear_assembly_sizes_v1& sizes)
        : active_dof_indices(sizes.active_dof_count, 0xA5A5A5A5U),
          row_offsets(sizes.row_offset_count, UINT64_C(0xA5A5A5A5A5A5A5A5)),
          column_indices(sizes.structural_entry_count, 0xA5A5A5A5U),
          tangent(sizes.structural_entry_count, -123.25),
          consistent_mass(sizes.structural_entry_count, -123.25),
          internal_force(sizes.active_dof_count, -123.25),
          external_load(sizes.active_dof_count, -123.25),
          equilibrium_residual(sizes.active_dof_count, -123.25),
          jvp(sizes.active_dof_count, -123.25),
          recovery_stable_indices(
              sizes.recovery_record_count,
              UINT64_C(0xA5A5A5A5A5A5A5A5)),
          recovery_element_types(sizes.recovery_record_count, 0xA5A5A5A5U),
          recovery_offsets(
              sizes.recovery_offset_count,
              UINT64_C(0xA5A5A5A5A5A5A5A5)),
          recovery_values(sizes.recovery_value_count, -123.25),
          model_content_hash(sizes.model_identity_length, 0xA5U),
          model_semantic_hash(sizes.model_identity_length, 0xA5U),
          model_provenance_hash(sizes.model_identity_length, 0xA5U) {}

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

[[nodiscard]] std::array<sa_mut_buffer_view_v1*, 16> output_views(
    sa_model_ir_linear_assembly_outputs_v1& outputs) {
    return {
        &outputs.active_dof_indices,
        &outputs.row_offsets,
        &outputs.column_indices,
        &outputs.tangent,
        &outputs.consistent_mass,
        &outputs.internal_force,
        &outputs.external_load,
        &outputs.equilibrium_residual,
        &outputs.jvp,
        &outputs.recovery_stable_indices,
        &outputs.recovery_element_types,
        &outputs.recovery_offsets,
        &outputs.recovery_values,
        &outputs.model_content_hash,
        &outputs.model_semantic_hash,
        &outputs.model_provenance_hash,
    };
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* const data,
    const std::size_t size) {
    const auto api = load_api();
    structural::tests::ModelIrAssemblyFixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    if (api.model_ir_create(&fixture.descriptor, &handle, nullptr) != SA_OK) {
        fail();
    }

    auto sizes = empty_sizes();
    if (api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) != SA_OK) {
        fail();
    }
    const auto mode = size == 0U ? std::uint8_t {0U} : data[0] % 35U;
    if (mode >= 32U) {
        auto probe = sizes;
        if (mode == 32U) {
            probe.abi_version = SA_ABI_V1_12;
        } else if (mode == 33U) {
            probe.struct_size = 8U;
        } else {
            probe.reserved[0] = 1U;
        }
        const auto before = probe;
        const auto status = api.model_ir_linear_assembly_sizes(handle, &probe, nullptr);
        if (status == SA_OK || std::memcmp(&probe, &before, sizeof(probe)) != 0) {
            fail();
        }
        if (api.model_ir_destroy(handle, nullptr) != SA_OK) {
            fail();
        }
        return 0;
    }

    auto displacement = structural::tests::assembly_displacement();
    auto direction = structural::tests::assembly_direction();
    std::array<char, 128> selector {};
    std::fill(selector.begin(), selector.end(), 'a');
    if (size > 2U) {
        const auto copy_size = std::min(size - 2U, selector.size());
        std::memcpy(selector.data(), data + 2U, copy_size);
    }
    auto config = sa_model_ir_linear_assembly_config_v1 {
        SA_ABI_V1_13,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_config_v1)),
        structural::tests::text("lp"),
        input_view(displacement.data(), displacement.size()),
        input_view(direction.data(), direction.size()),
        0U,
        {0U, 0U},
    };
    OutputStorage storage(sizes);
    const auto storage_before = storage;
    auto outputs = storage.descriptor();
    auto views = output_views(outputs);
    auto result = empty_result();
    const auto result_before = result;
    const auto selected = size > 1U ? static_cast<std::size_t>(data[1]) % views.size() : 0U;

    switch (mode) {
    case 1U:
        config.abi_version = SA_ABI_V1_12;
        break;
    case 2U:
        config.struct_size = 8U;
        break;
    case 3U:
        config.flags = 1U;
        break;
    case 4U:
        config.reserved[0] = 1U;
        break;
    case 5U:
        config.load_pattern_id = {nullptr, 1U};
        break;
    case 6U:
        config.load_pattern_id = {selector.data(), selector.size()};
        break;
    case 7U:
        config.displacement.abi_version = SA_ABI_V1_12;
        break;
    case 8U:
        config.displacement.struct_size = 8U;
        break;
    case 9U:
        config.displacement.length = std::numeric_limits<std::uint64_t>::max();
        break;
    case 10U:
        config.displacement.stride_bytes = size > 2U ? data[2] : 0U;
        break;
    case 11U:
        config.displacement.memory_space = SA_MEMORY_SPACE_DEVICE;
        break;
    case 12U:
        config.displacement.device_id = 0;
        break;
    case 13U:
        config.displacement.flags = 1U;
        break;
    case 14U:
        views[selected]->length += (size > 2U && (data[2] & 1U) != 0U)
            ? std::numeric_limits<std::uint64_t>::max()
            : 1U;
        break;
    case 15U:
        views[selected]->stride_bytes = size > 2U ? data[2] : 0U;
        break;
    case 16U:
        views[selected]->element_type = size > 2U ? data[2] : 0U;
        break;
    case 17U:
        views[selected]->memory_space = SA_MEMORY_SPACE_DEVICE;
        views[selected]->device_id = 0;
        break;
    case 18U:
        views[selected]->data = nullptr;
        break;
    case 19U:
        views[selected]->data = views[(selected + 1U) % views.size()]->data;
        break;
    case 20U:
        config.displacement.data = outputs.tangent.data;
        break;
    case 21U:
        config.displacement.data = config.direction.data;
        break;
    case 22U:
        result.reserved[0] = 1U;
        break;
    case 23U:
        outputs.reserved[0] = 1U;
        break;
    case 24U:
        outputs.struct_size = 8U;
        break;
    case 25U:
        result.struct_size = 8U;
        break;
    case 26U:
        result.abi_version = SA_ABI_V1_12;
        break;
    case 27U:
        outputs.abi_version = SA_ABI_V1_12;
        break;
    case 28U:
        if (size > 2U) {
            const auto copy_size = std::min(size - 2U, sizeof(displacement[0]));
            std::memcpy(&displacement[0], data + 2U, copy_size);
        } else {
            displacement[0] = 1.0;
        }
        break;
    case 29U:
        if (size > 2U) {
            const auto copy_size = std::min(size - 2U, sizeof(direction[6]));
            std::memcpy(&direction[6], data + 2U, copy_size);
        }
        break;
    case 30U:
        outputs.tangent.data = static_cast<void*>(
            static_cast<std::uint8_t*>(outputs.tangent.data) + 1U);
        break;
    case 31U:
        views[selected]->length = std::numeric_limits<std::uint64_t>::max();
        break;
    default:
        break;
    }

    const auto status =
        api.model_ir_linear_assemble(handle, &config, &outputs, &result, nullptr);
    if (status == SA_OK) {
        if (result.global_dof_count != sizes.global_dof_count
            || result.active_dof_count != sizes.active_dof_count
            || result.row_offset_count != sizes.row_offset_count
            || result.structural_entry_count != sizes.structural_entry_count
            || result.recovery_record_count != sizes.recovery_record_count
            || result.recovery_value_count != sizes.recovery_value_count
            || result.execution_backend != SA_EXECUTION_BACKEND_CPU
            || result.fallback_count != 0U) {
            fail();
        }
    } else if (!(storage == storage_before)
               || std::memcmp(&result, &result_before, sizeof(result)) != 0) {
        fail();
    }
    if (api.model_ir_destroy(handle, nullptr) != SA_OK) {
        fail();
    }
    return 0;
}
