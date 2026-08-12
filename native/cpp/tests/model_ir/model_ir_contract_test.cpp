#include "structural/abi_v1.h"

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

[[nodiscard]] sa_string_view_v1 text(const char* const value) {
    return {value, static_cast<std::uint64_t>(std::strlen(value))};
}

[[nodiscard]] sa_optional_string_view_v1 absent_text() {
    return {{nullptr, 0U}, 0U, 0U};
}

[[nodiscard]] sa_optional_string_view_v1 present_text(const char* const value) {
    return {text(value), 1U, 0U};
}

[[nodiscard]] sa_entity_identity_v1 entity(const char* const id, const std::uint64_t index) {
    return {
        SA_ABI_V1_1,
        static_cast<std::uint32_t>(sizeof(sa_entity_identity_v1)),
        text(id),
        index,
        absent_text(),
        text("{}"),
    };
}

[[nodiscard]] bool near(const double actual, const double expected) {
    return std::abs(actual - expected) <= std::max(1.0, std::abs(expected)) * 1.0e-12;
}

struct Fixture {
    std::array<char, 2> canonical {'{', '}'};
    std::array<char, 5> model_id {'m', 'o', 'd', 'e', 'l'};
    std::array<sa_dof_v1, 6> canonical_dofs {
        SA_DOF_UX,
        SA_DOF_UY,
        SA_DOF_UZ,
        SA_DOF_RX,
        SA_DOF_RY,
        SA_DOF_RZ,
    };
    std::array<sa_dof_v1, 6> fixed_dofs = canonical_dofs;
    std::array<sa_dof_v1, 5> guided_dofs {
        SA_DOF_UY,
        SA_DOF_UZ,
        SA_DOF_RX,
        SA_DOF_RY,
        SA_DOF_RZ,
    };
    std::array<sa_node_descriptor_v1, 2> nodes {};
    std::array<sa_material_descriptor_v1, 1> materials {};
    std::array<sa_section_descriptor_v1, 1> sections {};
    std::array<sa_element_descriptor_v1, 1> elements {};
    std::array<sa_constraint_descriptor_v1, 2> constraints {};
    std::array<sa_nodal_load_descriptor_v1, 1> nodal_loads {};
    std::array<sa_load_pattern_descriptor_v1, 1> load_patterns {};
    sa_model_ir_descriptor_v1 descriptor {};

    Fixture() {
        nodes[0] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_node_descriptor_v1)),
            entity("n0", 0U),
            {0.0, 0.0, 0.0},
        };
        nodes[1] = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_node_descriptor_v1)),
            entity("n1", 1U),
            {1.0, 0.0, 0.0},
        };

        materials[0].abi_version = SA_ABI_V1_1;
        materials[0].struct_size = static_cast<std::uint32_t>(sizeof(sa_material_descriptor_v1));
        materials[0].identity = entity("mat", 0U);
        materials[0].law_id = SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC;
        materials[0].parameter_set_version = 1U;
        materials[0].parameters.linear = {2.0e11, 0.3, 7850.0};
        materials[0].stateful = 0U;
        materials[0].state_update_epoch = SA_MATERIAL_STATE_EPOCH_NONE;
        materials[0].supports_trial_commit_rollback = 1U;
        materials[0].admissibility.abi_version = SA_ABI_V1_1;
        materials[0].admissibility.struct_size =
            static_cast<std::uint32_t>(sizeof(sa_material_admissibility_v1));

        sections[0].abi_version = SA_ABI_V1_1;
        sections[0].struct_size = static_cast<std::uint32_t>(sizeof(sa_section_descriptor_v1));
        sections[0].identity = entity("sec", 0U);
        sections[0].family_id = SA_SECTION_FRAME_3D;
        sections[0].parameter_set_version = 1U;
        sections[0].parameters.frame = {0.01, 1.0e-5, 1.0e-5, 2.0e-5, 0.01, 0.01};
        sections[0].steel_material_id = absent_text();
        sections[0].concrete_material_id = absent_text();

        elements[0].abi_version = SA_ABI_V1_1;
        elements[0].struct_size = static_cast<std::uint32_t>(sizeof(sa_element_descriptor_v1));
        elements[0].identity = entity("e0", 0U);
        elements[0].type = SA_ELEMENT_FRAME_3D;
        elements[0].formulation = SA_FORMULATION_EULER_BERNOULLI_3D;
        elements[0].node_ids[0] = text("n0");
        elements[0].node_ids[1] = text("n1");
        elements[0].material_id = present_text("mat");
        elements[0].section_id = text("sec");
        elements[0].has_local_axis_rotation = 1U;

        constraints[0].abi_version = SA_ABI_V1_1;
        constraints[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_constraint_descriptor_v1));
        constraints[0].identity = entity("c0", 0U);
        constraints[0].node_id = text("n0");
        constraints[0].dofs = fixed_dofs.data();
        constraints[0].dof_count = fixed_dofs.size();
        constraints[1].abi_version = SA_ABI_V1_1;
        constraints[1].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_constraint_descriptor_v1));
        constraints[1].identity = entity("c1", 1U);
        constraints[1].node_id = text("n1");
        constraints[1].dofs = guided_dofs.data();
        constraints[1].dof_count = guided_dofs.size();

        nodal_loads[0].abi_version = SA_ABI_V1_1;
        nodal_loads[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_nodal_load_descriptor_v1));
        nodal_loads[0].identity = entity("load0", 0U);
        nodal_loads[0].node_id = text("n1");
        nodal_loads[0].components_si[0] = 1.0;

        load_patterns[0].abi_version = SA_ABI_V1_1;
        load_patterns[0].struct_size =
            static_cast<std::uint32_t>(sizeof(sa_load_pattern_descriptor_v1));
        load_patterns[0].identity = entity("lp0", 0U);
        load_patterns[0].analysis_type = SA_ANALYSIS_LINEAR_STATIC;
        load_patterns[0].nodal_loads = nodal_loads.data();
        load_patterns[0].nodal_load_count = nodal_loads.size();

        descriptor.abi_version = SA_ABI_V1_1;
        descriptor.struct_size = static_cast<std::uint32_t>(sizeof(sa_model_ir_descriptor_v1));
        descriptor.schema_version = text("structural-analysis-model-ir.v2");
        descriptor.model_id = {model_id.data(), model_id.size()};
        descriptor.capability_profile = SA_MODEL_IR_PROFILE_GENERAL;
        descriptor.canonical_units = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_source_units_v1)),
            SA_LENGTH_UNIT_M,
            SA_FORCE_UNIT_N,
            SA_MASS_UNIT_KG,
            SA_TIME_UNIT_S,
            SA_ROTATION_UNIT_RAD,
            0U,
        };
        descriptor.coordinate_system = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_coordinate_system_descriptor_v1)),
            1U,
            1U,
            1U,
            1U,
            {0.0, 0.0, 0.0},
        };
        descriptor.dof_components = canonical_dofs.data();
        descriptor.dof_component_count = canonical_dofs.size();
        descriptor.provenance.abi_version = SA_ABI_V1_1;
        descriptor.provenance.struct_size =
            static_cast<std::uint32_t>(sizeof(sa_provenance_descriptor_v1));
        descriptor.provenance.source_format = SA_SOURCE_FORMAT_GENERATED;
        descriptor.provenance.source_ref = text("unit-test");
        descriptor.provenance.source_sha256 = text(
            "sha256:0000000000000000000000000000000000000000000000000000000000000000");
        descriptor.provenance.normalizer_id = text("native-test");
        descriptor.provenance.normalizer_version = text("1");
        descriptor.provenance.source_units = descriptor.canonical_units;
        descriptor.provenance.unit_scales_to_si = {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(sizeof(sa_unit_scales_v1)),
            1.0,
            1.0,
            1.0,
            1.0,
            1.0,
        };
        descriptor.provenance.extensions_json = text("{}");
        descriptor.nodes = nodes.data();
        descriptor.node_count = nodes.size();
        descriptor.materials = materials.data();
        descriptor.material_count = materials.size();
        descriptor.sections = sections.data();
        descriptor.section_count = sections.size();
        descriptor.elements = elements.data();
        descriptor.element_count = elements.size();
        descriptor.constraints = constraints.data();
        descriptor.constraint_count = constraints.size();
        descriptor.load_patterns = load_patterns.data();
        descriptor.load_pattern_count = load_patterns.size();
        descriptor.extensions_json = text("{}");
        descriptor.canonical_json = {canonical.data(), canonical.size()};
        descriptor.content_hash = text(
            "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
        descriptor.semantic_hash = text(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111");
        descriptor.provenance_hash = text(
            "sha256:2222222222222222222222222222222222222222222222222222222222222222");
    }
};

[[nodiscard]] sa_api_v1 load_api(const std::uint32_t version) {
    sa_api_request_v1 request {version, sizeof(sa_api_request_v1), 0U, {0U, 0U, 0U}};
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = sizeof(sa_api_v1);
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        return {};
    }
    return api;
}

[[nodiscard]] std::string report(const sa_api_v1& api, const sa_model_ir_handle_v1* handle) {
    std::uint64_t size = 0U;
    if (api.model_ir_validation_report_size(handle, &size, nullptr) != SA_OK) {
        return {};
    }
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    std::uint64_t written = 0U;
    if (api.model_ir_validation_report_write(
            handle, bytes.data(), bytes.size(), &written, nullptr)
        != SA_OK) {
        return {};
    }
    return {reinterpret_cast<const char*>(bytes.data()), static_cast<std::size_t>(written)};
}

[[nodiscard]] bool table_negotiates_minor_versions() {
    const auto old = load_api(SA_ABI_V1_0);
    CHECK(old.abi_version == SA_ABI_V1_0);
    CHECK(old.capabilities == SA_CAPABILITY_BUFFER_VALIDATION);
    CHECK(old.model_ir_create == nullptr);
    CHECK(old.model_ir_snapshot_write == nullptr);
    CHECK(old.model_ir_ndtha_adapt == nullptr);

    const auto current = load_api(SA_ABI_V1_1);
    CHECK(current.abi_version == SA_ABI_V1_1);
    CHECK((current.capabilities & SA_CAPABILITY_MODEL_IR_V2_TYPED) != 0U);
    CHECK((current.capabilities & SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT) != 0U);
    CHECK(current.model_ir_create != nullptr);
    CHECK(current.model_ir_destroy != nullptr);
    CHECK(current.model_ir_validation_report_size != nullptr);
    CHECK(current.model_ir_validation_report_write != nullptr);
    CHECK(current.model_ir_snapshot_size != nullptr);
    CHECK(current.model_ir_snapshot_write != nullptr);
    CHECK(current.model_ir_ndtha_adapt == nullptr);

    const auto restart = load_api(SA_ABI_V1_5);
    CHECK(restart.abi_version == SA_ABI_V1_5);
    CHECK(restart.model_ir_ndtha_adapt == nullptr);
    CHECK((restart.capabilities & SA_CAPABILITY_MODEL_IR_NDTHA_ADAPTER) == 0U);

    const auto adapter = load_api(SA_ABI_V1_6);
    CHECK(adapter.abi_version == SA_ABI_V1_6);
    CHECK(adapter.model_ir_ndtha_adapt != nullptr);
    CHECK((adapter.capabilities & SA_CAPABILITY_MODEL_IR_NDTHA_ADAPTER) != 0U);
    return true;
}

[[nodiscard]] bool create_deep_copies_and_exports_without_partial_writes() {
    const auto api = load_api(SA_ABI_V1_1);
    Fixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(handle != nullptr);
    fixture.canonical = {'x', 'x'};
    fixture.model_id = {'x', 'x', 'x', 'x', 'x'};

    const auto validation = report(api, handle);
    CHECK(validation.find("\"semantics_valid\":true") != std::string::npos);
    CHECK(validation.find("\"analysis_ready\":true") != std::string::npos);
    CHECK(validation.find("\"model_id\":\"model\"") != std::string::npos);

    std::uint64_t snapshot_size = 0U;
    CHECK(api.model_ir_snapshot_size(handle, &snapshot_size, nullptr) == SA_OK);
    CHECK(snapshot_size == 2U);
    std::array<std::uint8_t, 2> tiny {'a', 'b'};
    std::uint64_t written = 77U;
    CHECK(api.model_ir_snapshot_write(handle, tiny.data(), 1U, &written, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    CHECK(tiny[0] == static_cast<std::uint8_t>('a'));
    CHECK(written == 77U);
    CHECK(api.model_ir_snapshot_write(handle, tiny.data(), tiny.size(), &written, nullptr) == SA_OK);
    CHECK(written == 2U);
    CHECK(tiny[0] == static_cast<std::uint8_t>('{'));
    CHECK(tiny[1] == static_cast<std::uint8_t>('}'));
    auto* const stale_handle = handle;
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    CHECK(api.model_ir_destroy(stale_handle, nullptr) == SA_ERR_INVALID_ARGUMENT);
    return true;
}

[[nodiscard]] bool failed_create_is_atomic_and_semantic_failures_are_reports() {
    const auto api = load_api(SA_ABI_V1_1);
    Fixture fixture;
    auto* const sentinel = reinterpret_cast<sa_model_ir_handle_v1*>(
        static_cast<std::uintptr_t>(0x1234U));
    auto* output = sentinel;
    fixture.descriptor.struct_size = sizeof(sa_header_v1);
    CHECK(api.model_ir_create(&fixture.descriptor, &output, nullptr) == SA_ERR_STRUCT_SIZE);
    CHECK(output == sentinel);

    fixture.descriptor.struct_size = sizeof(sa_model_ir_descriptor_v1);
    fixture.descriptor.nodes = nullptr;
    output = sentinel;
    CHECK(api.model_ir_create(&fixture.descriptor, &output, nullptr) == SA_ERR_INVALID_ARGUMENT);
    CHECK(output == sentinel);

    fixture.descriptor.nodes = fixture.nodes.data();
    fixture.nodes[1].identity.extensions_json = {nullptr, 2U};
    output = sentinel;
    CHECK(api.model_ir_create(&fixture.descriptor, &output, nullptr) == SA_ERR_INVALID_ARGUMENT);
    CHECK(output == sentinel);
    fixture.nodes[1].identity.extensions_json = text("{}");

    fixture.descriptor.provenance.unit_scales_to_si.length_to_m = 10.0;
    output = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &output, nullptr) == SA_OK);
    CHECK(report(api, output).find("unit_scale_mismatch") != std::string::npos);
    CHECK(report(api, output).find("\"analysis_ready\":false") != std::string::npos);
    CHECK(api.model_ir_destroy(output, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool references_cycles_time_and_readiness_are_fail_closed() {
    const auto api = load_api(SA_ABI_V1_1);
    Fixture fixture;
    fixture.elements[0].node_ids[1] = text("missing");
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("dangling_reference") != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    fixture.elements[0].node_ids[1] = text("n1");

    std::array<sa_load_combination_term_v1, 2> terms {{
        {SA_ABI_V1_1, sizeof(sa_load_combination_term_v1), text("cb"), SA_LOAD_REF_COMBINATION,
            0U, 1.0},
        {SA_ABI_V1_1, sizeof(sa_load_combination_term_v1), text("ca"), SA_LOAD_REF_COMBINATION,
            0U, 1.0},
    }};
    std::array<sa_load_combination_descriptor_v1, 2> combinations {{
        {SA_ABI_V1_1, sizeof(sa_load_combination_descriptor_v1), entity("ca", 0U),
            &terms[0], 1U},
        {SA_ABI_V1_1, sizeof(sa_load_combination_descriptor_v1), entity("cb", 1U),
            &terms[1], 1U},
    }};
    fixture.descriptor.load_combinations = combinations.data();
    fixture.descriptor.load_combination_count = combinations.size();
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("load_combination_cycle") != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    fixture.descriptor.load_combinations = nullptr;
    fixture.descriptor.load_combination_count = 0U;

    std::array<sa_time_point_v1, 2> points {{{1.0, 0.0}, {1.0, 1.0}}};
    std::array<sa_time_function_descriptor_v1, 1> time_functions {{
        {SA_ABI_V1_1, sizeof(sa_time_function_descriptor_v1), text("tf"), 0U, points.data(),
            points.size(), text("{}")},
    }};
    fixture.descriptor.time_functions = time_functions.data();
    fixture.descriptor.time_function_count = time_functions.size();
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("time_function_not_strictly_increasing")
          != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    fixture.descriptor.time_functions = nullptr;
    fixture.descriptor.time_function_count = 0U;

    std::array<sa_unsupported_feature_descriptor_v1, 1> unsupported {{
        {SA_ABI_V1_1, sizeof(sa_unsupported_feature_descriptor_v1), text("feature.block"),
            text("test"), absent_text(), SA_UNSUPPORTED_BLOCKED, 1U, text("blocked by test"),
            text("{}")},
    }};
    fixture.descriptor.unsupported_features = unsupported.data();
    fixture.descriptor.unsupported_feature_count = unsupported.size();
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    const auto validation = report(api, handle);
    CHECK(validation.find("\"semantics_valid\":true") != std::string::npos);
    CHECK(validation.find("\"analysis_ready\":false") != std::string::npos);
    CHECK(validation.find("feature.block") != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);

    fixture.descriptor.unsupported_features = nullptr;
    fixture.descriptor.unsupported_feature_count = 0U;
    std::array<sa_roundtrip_row_descriptor_v1, 1> roundtrip {{
        {SA_ABI_V1_1, sizeof(sa_roundtrip_row_descriptor_v1), text("src"),
            SA_MODEL_IR_ENTITY_NODE, 0U, text("n0"), SA_ROUNDTRIP_UNSUPPORTED, 0U, text("{}")},
    }};
    fixture.descriptor.roundtrip_rows = roundtrip.data();
    fixture.descriptor.roundtrip_row_count = roundtrip.size();
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("derived.roundtrip.unsupported.6c90675ac0e2ff73")
          != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);

    fixture.descriptor.roundtrip_rows = nullptr;
    fixture.descriptor.roundtrip_row_count = 0U;
    fixture.descriptor.capability_profile =
        SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("bounded_frame3d_material_law_unsupported")
          != std::string::npos);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

[[nodiscard]] bool immutable_queries_are_concurrent() {
    const auto api = load_api(SA_ABI_V1_1);
    Fixture fixture;
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    for (std::size_t worker = 0U; worker < 8U; ++worker) {
        workers.emplace_back([&api, handle, &passed] {
            for (std::size_t iteration = 0U; iteration < 256U; ++iteration) {
                std::uint64_t size = 0U;
                if (api.model_ir_snapshot_size(handle, &size, nullptr) != SA_OK || size != 2U
                    || report(api, handle).empty()) {
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

struct AdapterOutputStorage {
    std::array<double, 1> stiffness {41.0};
    std::array<double, 1> height {42.0};
    std::array<double, 1> axial {43.0};
    std::array<double, 1> yield_drift {44.0};
    std::array<double, 1> mass {45.0};
    std::array<double, 1> damping {46.0};
    std::array<double, 1> floor_load {47.0};

    [[nodiscard]] bool operator==(const AdapterOutputStorage&) const = default;
};

[[nodiscard]] sa_buffer_view_v1 adapter_input_view(
    const double* const data,
    const std::uint64_t length) {
    return {
        SA_ABI_V1_6,
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

[[nodiscard]] sa_mut_buffer_view_v1 adapter_output_view(std::array<double, 1>& values) {
    return {
        SA_ABI_V1_6,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_model_ir_ndtha_adapter_outputs_v1 adapter_outputs(
    AdapterOutputStorage& storage) {
    return {
        SA_ABI_V1_6,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_ndtha_adapter_outputs_v1)),
        adapter_output_view(storage.stiffness),
        adapter_output_view(storage.height),
        adapter_output_view(storage.axial),
        adapter_output_view(storage.yield_drift),
        adapter_output_view(storage.mass),
        adapter_output_view(storage.damping),
        adapter_output_view(storage.floor_load),
        {0U, 0U},
    };
}

[[nodiscard]] sa_model_ir_ndtha_adapter_request_v1 adapter_request(
    const std::array<double, 3>& acceleration) {
    sa_nonlinear_ndtha_config_v1 config {};
    config.abi_version = SA_ABI_V1_6;
    config.struct_size = static_cast<std::uint32_t>(sizeof(config));
    config.story_count = 1U;
    config.step_count = static_cast<std::uint32_t>(acceleration.size());
    config.dt_s = 0.01;
    config.newmark_beta = 0.25;
    config.newmark_gamma = 0.5;
    config.tolerance = 1.0e-5;
    config.max_step_iterations = 16U;
    config.adaptive_load_decay = 0.82;
    config.damping_force_cap_ratio = 0.6;
    config.newton_max_iter = 120U;
    config.line_search_decay = 0.5;
    config.line_search_min = 0.03125;
    config.hardening_ratio = 0.2;
    config.pdelta_factor = 0.0;
    config.collapse_drift_threshold_pct = 10.0;
    return {
        SA_ABI_V1_6,
        static_cast<std::uint32_t>(sizeof(sa_model_ir_ndtha_adapter_request_v1)),
        SA_MODEL_IR_NDTHA_ADAPTER_FIXED_GUIDED_FRAME3D_X_V1,
        0U,
        text("e0"),
        text("n0"),
        text("n1"),
        text("lp0"),
        0.00025,
        0.01,
        config,
        adapter_input_view(acceleration.data(), acceleration.size()),
        {0U, 0U},
    };
}

void configure_adapter_model(Fixture& fixture) {
    fixture.nodes[1].coordinates_m[0] = 0.0;
    fixture.nodes[1].coordinates_m[2] = 3.2;
    fixture.materials[0].parameters.linear.density_kg_m3 = 2500.0;
    fixture.sections[0].parameters.frame = {
        1.25,
        50'000'000.0 * 3.2 * 3.2 * 3.2 / (12.0 * 2.0e11),
        0.001,
        0.001,
        1.0,
        1.0,
    };
    fixture.nodal_loads[0].components_si[0] = 200'000.0;
}

[[nodiscard]] bool bounded_ndtha_adapter_is_atomic_and_thread_safe() {
    const auto api = load_api(SA_ABI_V1_6);
    Fixture fixture;
    configure_adapter_model(fixture);
    std::array<sa_prescribed_value_v1, 6> fixed_zeros {};
    for (std::size_t index = 0U; index < fixed_zeros.size(); ++index) {
        fixed_zeros[index].dof = fixture.fixed_dofs[index];
    }
    std::array<sa_prescribed_value_v1, 5> guided_zeros {};
    for (std::size_t index = 0U; index < guided_zeros.size(); ++index) {
        guided_zeros[index].dof = fixture.guided_dofs[index];
    }
    fixture.constraints[0].prescribed_values = fixed_zeros.data();
    fixture.constraints[0].prescribed_value_count = fixed_zeros.size();
    fixture.constraints[1].prescribed_values = guided_zeros.data();
    fixture.constraints[1].prescribed_value_count = guided_zeros.size();
    std::array<sa_roundtrip_row_descriptor_v1, 1> provenance_roundtrip {{
        {SA_ABI_V1_1, sizeof(sa_roundtrip_row_descriptor_v1), text("NODE:1"),
            SA_MODEL_IR_ENTITY_NODE, 0U, text("n0"), SA_ROUNDTRIP_CANONICALIZED, 0U,
            text("{}")},
    }};
    fixture.descriptor.roundtrip_rows = provenance_roundtrip.data();
    fixture.descriptor.roundtrip_row_count = provenance_roundtrip.size();
    sa_model_ir_handle_v1* handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    CHECK(report(api, handle).find("\"analysis_ready\":true") != std::string::npos);

    const std::array<double, 3> acceleration {0.0, 0.05, -0.03};
    auto request = adapter_request(acceleration);
    AdapterOutputStorage storage;
    auto outputs = adapter_outputs(storage);
    sa_model_ir_ndtha_adapter_result_v1 result {};
    result.abi_version = SA_ABI_V1_6;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    CHECK(api.model_ir_ndtha_adapt(handle, &request, &outputs, &result, nullptr) == SA_OK);
    CHECK(near(storage.stiffness[0], 50'000'000.0));
    CHECK(near(storage.height[0], 3.2));
    CHECK(storage.axial[0] == 0.0);
    CHECK(storage.yield_drift[0] == 0.01);
    CHECK(near(storage.mass[0], 5000.0));
    CHECK(near(storage.damping[0], 250.0));
    CHECK(storage.floor_load[0] == 200'000.0);
    CHECK(result.profile == SA_MODEL_IR_NDTHA_ADAPTER_FIXED_GUIDED_FRAME3D_X_V1);
    CHECK(result.story_count == 1U);
    CHECK(result.element_index == 0U);
    CHECK(result.load_pattern_index == 0U);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);

    AdapterOutputStorage unchanged;
    const auto before = unchanged;
    auto invalid_outputs = adapter_outputs(unchanged);
    invalid_outputs.story_height_m.data = invalid_outputs.story_stiffness_n_per_m.data;
    sa_model_ir_ndtha_adapter_result_v1 failed {};
    failed.abi_version = SA_ABI_V1_6;
    failed.struct_size = static_cast<std::uint32_t>(sizeof(failed));
    failed.story_count = 77U;
    CHECK(api.model_ir_ndtha_adapt(handle, &request, &invalid_outputs, &failed, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(unchanged == before);
    CHECK(failed.story_count == 77U);

    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    for (std::size_t worker = 0U; worker < 8U; ++worker) {
        workers.emplace_back([api, handle, &passed] {
            const std::array<double, 3> worker_acceleration {0.0, 0.05, -0.03};
            const auto worker_request = adapter_request(worker_acceleration);
            AdapterOutputStorage worker_storage;
            const auto worker_outputs = adapter_outputs(worker_storage);
            sa_model_ir_ndtha_adapter_result_v1 worker_result {};
            worker_result.abi_version = SA_ABI_V1_6;
            worker_result.struct_size = static_cast<std::uint32_t>(sizeof(worker_result));
            for (std::size_t iteration = 0U; iteration < 128U; ++iteration) {
                if (api.model_ir_ndtha_adapt(
                        handle,
                        &worker_request,
                        &worker_outputs,
                        &worker_result,
                        nullptr)
                        != SA_OK
                    || !near(worker_storage.stiffness[0], 50'000'000.0)) {
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

    fixed_zeros[0].value_si = 0.001;
    handle = nullptr;
    CHECK(api.model_ir_create(&fixture.descriptor, &handle, nullptr) == SA_OK);
    AdapterOutputStorage prescribed_storage;
    auto prescribed_outputs = adapter_outputs(prescribed_storage);
    sa_model_ir_ndtha_adapter_result_v1 prescribed_result {};
    prescribed_result.abi_version = SA_ABI_V1_6;
    prescribed_result.struct_size = static_cast<std::uint32_t>(sizeof(prescribed_result));
    CHECK(api.model_ir_ndtha_adapt(
              handle, &request, &prescribed_outputs, &prescribed_result, nullptr)
          == SA_ERR_ANALYSIS_NOT_READY);
    CHECK(api.model_ir_destroy(handle, nullptr) == SA_OK);
    return true;
}

} // namespace

int main() {
    const std::array tests {
        table_negotiates_minor_versions,
        create_deep_copies_and_exports_without_partial_writes,
        failed_create_is_atomic_and_semantic_failures_are_reports,
        references_cycles_time_and_readiness_are_fail_closed,
        immutable_queries_are_concurrent,
        bounded_ndtha_adapter_is_atomic_and_thread_safe,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
