#include "structural/abi_v1.h"

#include "model_ir_assembly_fixture.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

[[nodiscard]] bool near(const double left, const double right) {
    return std::abs(left - right) <= 1.0e-12;
}

struct ErrorStorage final {
    std::array<char, 256> bytes {};
    sa_error_buffer_v1 descriptor {
        SA_ABI_V1_15,
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

[[nodiscard]] sa_buffer_view_v1 input_view(
    const double* const data,
    const std::uint64_t length) {
    return {
        SA_ABI_V1_15,
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
        SA_ABI_V1_15,
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

struct BucklingOutputStorage final {
    std::vector<std::uint32_t> active_dof_indices;
    std::vector<std::uint64_t> row_offsets;
    std::vector<std::uint32_t> column_indices;
    std::vector<double> geometric_stiffness;
    std::vector<std::uint64_t> frame_stable_indices;
    std::vector<double> frame_axial_compression_n;
    std::vector<std::uint8_t> model_content_hash;
    std::vector<std::uint8_t> model_semantic_hash;
    std::vector<std::uint8_t> model_provenance_hash;

    explicit BucklingOutputStorage(
        const sa_model_ir_linear_assembly_sizes_v1& sizes,
        const bool sentinel = false)
        : active_dof_indices(sizes.active_dof_count, sentinel ? 0xA5A5A5A5U : 0U),
          row_offsets(sizes.row_offset_count, sentinel ? UINT64_C(0xA5A5A5A5A5A5A5A5) : 0U),
          column_indices(sizes.structural_entry_count, sentinel ? 0xA5A5A5A5U : 0U),
          geometric_stiffness(sizes.structural_entry_count, sentinel ? -123.25 : 0.0),
          frame_stable_indices(
              sizes.recovery_record_count,
              sentinel ? UINT64_C(0xA5A5A5A5A5A5A5A5) : 0U),
          frame_axial_compression_n(sizes.recovery_record_count, sentinel ? -123.25 : 0.0),
          model_content_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U),
          model_semantic_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U),
          model_provenance_hash(sizes.model_identity_length, sentinel ? 0xA5U : 0U) {}

    [[nodiscard]] sa_model_ir_linear_buckling_assembly_outputs_v1 descriptor() {
        return {
            SA_ABI_V1_15,
            static_cast<std::uint32_t>(
                sizeof(sa_model_ir_linear_buckling_assembly_outputs_v1)),
            output_view(active_dof_indices, SA_ELEMENT_TYPE_U32),
            output_view(row_offsets, SA_ELEMENT_TYPE_U64),
            output_view(column_indices, SA_ELEMENT_TYPE_U32),
            output_view(geometric_stiffness, SA_ELEMENT_TYPE_F64),
            output_view(frame_stable_indices, SA_ELEMENT_TYPE_U64),
            output_view(frame_axial_compression_n, SA_ELEMENT_TYPE_F64),
            output_view(model_content_hash, SA_ELEMENT_TYPE_U8),
            output_view(model_semantic_hash, SA_ELEMENT_TYPE_U8),
            output_view(model_provenance_hash, SA_ELEMENT_TYPE_U8),
            {0U, 0U},
        };
    }

    [[nodiscard]] bool operator==(const BucklingOutputStorage&) const = default;
};

[[nodiscard]] sa_model_ir_linear_assembly_sizes_v1 empty_sizes() {
    sa_model_ir_linear_assembly_sizes_v1 sizes {};
    sizes.abi_version = SA_ABI_V1_13;
    sizes.struct_size =
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_assembly_sizes_v1));
    return sizes;
}

[[nodiscard]] sa_model_ir_linear_buckling_assembly_result_v1 empty_result() {
    sa_model_ir_linear_buckling_assembly_result_v1 result {};
    result.abi_version = SA_ABI_V1_15;
    result.struct_size =
        static_cast<std::uint32_t>(sizeof(sa_model_ir_linear_buckling_assembly_result_v1));
    return result;
}

void configure_compressed_cantilever(structural::tests::ModelIrAssemblyFixture& fixture) {
    fixture.descriptor.node_count = 2U;
    fixture.descriptor.section_count = 1U;
    fixture.descriptor.element_count = 1U;
    fixture.descriptor.constraint_count = 1U;
    fixture.elements[0].local_axis_rotation_rad = 0.0;
    fixture.elements[0].has_local_axis_rotation = 1U;
    fixture.nodal_loads[0].node_id = structural::tests::text("n1");
    fixture.nodal_loads[0].components_si[0] = -10.0;
    fixture.nodal_loads[0].components_si[1] = 0.0;
    fixture.load_patterns[0].nodal_load_count = 1U;
}

[[nodiscard]] bool table_is_append_only() {
    const auto previous = load_api(SA_ABI_V1_14);
    CHECK(previous.abi_version == SA_ABI_V1_14);
    CHECK((previous.capabilities & SA_CAPABILITY_MODEL_IR_LINEAR_BUCKLING_ASSEMBLY_CPU) == 0U);
    CHECK(previous.model_ir_linear_buckling_assemble == nullptr);

    const auto current = load_api(SA_ABI_V1_15);
    CHECK(current.abi_version == SA_ABI_V1_15);
    CHECK((current.capabilities & SA_CAPABILITY_MODEL_IR_LINEAR_BUCKLING_ASSEMBLY_CPU) != 0U);
    CHECK(current.model_ir_linear_buckling_assemble != nullptr);

    sa_api_v1 frozen_prefix {};
    frozen_prefix.abi_version = SA_ABI_V1_14;
    frozen_prefix.struct_size = SA_API_V1_14_MIN_SIZE;
    frozen_prefix.model_ir_linear_buckling_assemble = current.model_ir_linear_buckling_assemble;
    const sa_api_request_v1 request {
        SA_ABI_V1_14,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    CHECK(sa_get_api_v1(&request, &frozen_prefix, nullptr) == SA_OK);
    CHECK(frozen_prefix.abi_version == SA_ABI_V1_14);
    CHECK(frozen_prefix.struct_size == sizeof(sa_api_v1));
    CHECK(frozen_prefix.model_ir_linear_buckling_assemble
          == current.model_ir_linear_buckling_assemble);
    return true;
}

[[nodiscard]] bool compressed_frame_crosses_the_frozen_abi() {
    const auto api = load_api(SA_ABI_V1_15);
    structural::tests::ModelIrAssemblyFixture fixture;
    configure_compressed_cantilever(fixture);
    sa_model_ir_handle_v1* handle = nullptr;
    ErrorStorage error;
    const auto create_status = api.model_ir_create(&fixture.descriptor, &handle, &error.descriptor);
    if (create_status != SA_OK) {
        std::cerr << "ModelIR create failed: " << error.bytes.data() << '\n';
    }
    CHECK(create_status == SA_OK);

    auto sizes = empty_sizes();
    CHECK(api.model_ir_linear_assembly_sizes(handle, &sizes, nullptr) == SA_OK);
    CHECK(sizes.global_dof_count == 12U);
    CHECK(sizes.active_dof_count == 6U);
    CHECK(sizes.row_offset_count == 7U);
    CHECK(sizes.structural_entry_count == 36U);
    CHECK(sizes.recovery_record_count == 1U);
    CHECK(sizes.model_identity_length == 71U);

    std::array<double, 12> displacement {};
    displacement[6] = -10.0;
    const sa_model_ir_linear_buckling_assembly_config_v1 config {
        SA_ABI_V1_15,
        static_cast<std::uint32_t>(
            sizeof(sa_model_ir_linear_buckling_assembly_config_v1)),
        structural::tests::text("lp"),
        input_view(displacement.data(), displacement.size()),
        0U,
        {0U, 0U},
    };
    BucklingOutputStorage storage(sizes);
    auto outputs = storage.descriptor();
    auto result = empty_result();
    CHECK(api.model_ir_linear_buckling_assemble(
              handle, &config, &outputs, &result, nullptr)
          == SA_OK);
    CHECK(result.global_dof_count == 12U);
    CHECK(result.active_dof_count == 6U);
    CHECK(result.structural_entry_count == 36U);
    CHECK(result.frame_prestress_count == 1U);
    CHECK(result.load_pattern_index == 0U);
    CHECK(result.equilibrium_residual_inf_n == 0.0);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(storage.active_dof_indices
          == std::vector<std::uint32_t>({6U, 7U, 8U, 9U, 10U, 11U}));
    CHECK(storage.row_offsets
          == std::vector<std::uint64_t>({0U, 6U, 12U, 18U, 24U, 30U, 36U}));
    CHECK(storage.column_indices
          == std::vector<std::uint32_t>({
              0U, 1U, 2U, 3U, 4U, 5U,
              0U, 1U, 2U, 3U, 4U, 5U,
              0U, 1U, 2U, 3U, 4U, 5U,
              0U, 1U, 2U, 3U, 4U, 5U,
              0U, 1U, 2U, 3U, 4U, 5U,
              0U, 1U, 2U, 3U, 4U, 5U,
          }));
    const auto value = [&storage](const std::size_t row, const std::size_t column) {
        return storage.geometric_stiffness[row * 6U + column];
    };
    CHECK(near(value(1U, 1U), 6.0));
    CHECK(near(value(1U, 5U), -1.0));
    CHECK(near(value(2U, 2U), 6.0));
    CHECK(near(value(2U, 4U), 1.0));
    CHECK(near(value(4U, 2U), 1.0));
    CHECK(near(value(4U, 4U), 8.0 / 3.0));
    CHECK(near(value(5U, 1U), -1.0));
    CHECK(near(value(5U, 5U), 8.0 / 3.0));
    CHECK(storage.frame_stable_indices == std::vector<std::uint64_t>({0U}));
    CHECK(storage.frame_axial_compression_n == std::vector<double>({10.0}));
    CHECK(std::string(storage.model_content_hash.begin(), storage.model_content_hash.end())
          == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");

    BucklingOutputStorage rejected(sizes, true);
    const auto rejected_before = rejected;
    auto rejected_outputs = rejected.descriptor();
    auto rejected_result = empty_result();
    rejected_result.global_dof_count = UINT64_C(0xA5A5A5A5A5A5A5A5);
    const auto rejected_result_before = rejected_result;
    std::array<double, 12> non_equilibrium {};
    auto rejected_config = config;
    rejected_config.equilibrium_displacement =
        input_view(non_equilibrium.data(), non_equilibrium.size());
    CHECK(api.model_ir_linear_buckling_assemble(
              handle, &rejected_config, &rejected_outputs, &rejected_result, nullptr)
          == SA_ERR_RESIDUAL_LIMIT);
    CHECK(rejected == rejected_before);
    CHECK(std::memcmp(
              &rejected_result, &rejected_result_before, sizeof(rejected_result))
          == 0);

    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

}  // namespace

int main() {
    const std::array tests {
        table_is_append_only,
        compressed_frame_crosses_the_frozen_abi,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
