#include "model_ir.hpp"

#include "sha256.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <span>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <variant>
#include <vector>

namespace structural::model_ir {
namespace {

constexpr std::uint64_t kMaxFamilyRows = UINT64_C(1'000'000);
constexpr std::uint64_t kMaxNestedRows = UINT64_C(4'000'000);
constexpr std::uint64_t kMaxStringBytes = UINT64_C(1'048'576);
constexpr std::uint64_t kMaxSnapshotBytes = UINT64_C(67'108'864);
constexpr double kZeroLengthToleranceM = 1.0e-12;

struct Issue {
    std::string code;
    std::string path;
    std::string detail;

    [[nodiscard]] auto ordering_key() const noexcept {
        return std::tie(path, code, detail);
    }
};

struct Entity {
    std::string id;
    std::uint64_t index {};
    std::optional<std::string> source_id;
    std::string extensions;
};

struct SourceUnits {
    std::uint32_t length {};
    std::uint32_t force {};
    std::uint32_t mass {};
    std::uint32_t time {};
    std::uint32_t rotation {};
};

struct UnitScales {
    double length_to_m {};
    double force_to_n {};
    double mass_to_kg {};
    double time_to_s {};
    double rotation_to_rad {};
};

struct Provenance {
    std::uint32_t source_format {};
    std::string source_ref;
    std::string source_sha256;
    std::string normalizer_id;
    std::string normalizer_version;
    SourceUnits source_units;
    UnitScales unit_scales;
    std::string extensions;
};

struct Node {
    Entity identity;
    std::array<double, 3> coordinates {};
};

struct Admissibility {
    bool present {};
    std::string loading_domain;
    std::array<bool, 6> supports {};
};

using MaterialParameters = std::variant<
    sa_linear_material_parameters_v1,
    sa_steel_material_parameters_v1,
    sa_concrete_material_parameters_v1>;

struct Material {
    Entity identity;
    std::uint32_t law {};
    std::uint32_t parameter_set_version {};
    MaterialParameters parameters;
    bool stateful {};
    std::uint32_t state_update_epoch {};
    bool supports_trial_commit_rollback {};
    Admissibility admissibility;
};

using SectionParameters = std::variant<
    sa_frame_section_parameters_v1,
    sa_truss_section_parameters_v1,
    sa_rc_fiber_section_parameters_v1>;

struct Section {
    Entity identity;
    std::uint32_t family {};
    std::uint32_t parameter_set_version {};
    SectionParameters parameters;
    std::optional<std::string> steel_material_id;
    std::optional<std::string> concrete_material_id;
};

struct Element {
    Entity identity;
    std::uint32_t type {};
    std::uint32_t formulation {};
    std::array<std::string, 2> node_ids;
    std::optional<std::string> material_id;
    std::string section_id;
    std::optional<double> local_axis_rotation_rad;
    std::array<double, 3> offset_i {};
    std::array<double, 3> offset_j {};
    std::vector<std::uint32_t> releases_i;
    std::vector<std::uint32_t> releases_j;
    std::optional<std::uint64_t> integration_order;
    std::optional<std::array<double, 2>> uniform_load;
};

struct PrescribedValue {
    std::uint32_t dof {};
    double value {};
};

struct Constraint {
    Entity identity;
    std::string node_id;
    std::vector<std::uint32_t> dofs;
    std::vector<PrescribedValue> prescribed_values;
};

struct NodalLoad {
    Entity identity;
    std::string node_id;
    std::array<double, 6> components {};
};

struct LoadPattern {
    Entity identity;
    std::uint32_t analysis_type {};
    std::array<double, 3> self_weight {};
    std::vector<NodalLoad> nodal_loads;
};

struct CombinationTerm {
    std::string ref_id;
    std::uint32_t ref_kind {};
    double factor {};
};

struct LoadCombination {
    Entity identity;
    std::vector<CombinationTerm> terms;
};

struct TimeFunction {
    std::string id;
    std::uint64_t index {};
    std::vector<sa_time_point_v1> points;
    std::string extensions;
};

struct ConstructionStage {
    std::string id;
    std::uint64_t index {};
    std::vector<std::string> active_element_ids;
    std::vector<std::string> active_constraint_ids;
    std::vector<std::string> load_pattern_ids;
    std::string extensions;
};

struct RoundtripRow {
    std::string source_entity_id;
    std::uint32_t entity_kind {};
    std::string model_ir_entity_id;
    std::uint32_t mapping_status {};
    std::string extensions;
};

struct UnsupportedFeature {
    std::string feature_id;
    std::string kind;
    std::optional<std::string> source_entity_id;
    std::uint32_t disposition {};
    bool blocking {};
    std::string detail;
    std::string extensions;
};

struct OwnedModel {
    std::string schema_version;
    std::string model_id;
    std::uint32_t capability_profile {};
    SourceUnits canonical_units;
    std::array<double, 3> coordinate_origin {};
    std::vector<std::uint32_t> dof_components;
    Provenance provenance;
    std::vector<Node> nodes;
    std::vector<Material> materials;
    std::vector<Section> sections;
    std::vector<Element> elements;
    std::vector<Constraint> constraints;
    std::vector<LoadPattern> load_patterns;
    std::vector<LoadCombination> load_combinations;
    std::vector<TimeFunction> time_functions;
    std::vector<ConstructionStage> construction_stages;
    std::vector<RoundtripRow> roundtrip_rows;
    std::vector<UnsupportedFeature> unsupported_features;
    std::string extensions;
    std::string canonical_json;
    std::string content_hash;
    std::string semantic_hash;
    std::string provenance_hash;
};

[[noreturn]] void fail(const sa_status_code_v1 status, const char* const message) {
    throw Error(status, message);
}

void require_header(
    const std::uint32_t version,
    const std::uint32_t size,
    const std::size_t required_size) {
    if (SA_ABI_VERSION_MAJOR(version) != SA_ABI_VERSION_MAJOR(SA_ABI_V1_1)
        || SA_ABI_VERSION_MINOR(version) < SA_ABI_VERSION_MINOR(SA_ABI_V1_1)
        || SA_ABI_VERSION_MINOR(version) > SA_ABI_VERSION_MINOR(SA_ABI_V1_CURRENT)) {
        fail(SA_ERR_ABI_VERSION_MISMATCH, "ModelIR descriptor ABI is unsupported");
    }
    if (size < required_size) {
        fail(SA_ERR_STRUCT_SIZE, "ModelIR descriptor struct_size is too small");
    }
}

void require_boolean(const std::uint32_t value) {
    if (value > 1U) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR boolean field is not zero or one");
    }
}

void require_zero(const std::uint32_t value) {
    if (value != 0U) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR reserved field is not zero");
    }
}

[[nodiscard]] bool valid_utf8(const std::string_view value) noexcept {
    std::size_t index = 0U;
    while (index < value.size()) {
        const auto first = static_cast<unsigned char>(value[index]);
        if (first <= 0x7fU) {
            ++index;
            continue;
        }
        std::size_t width = 0U;
        if (first >= 0xc2U && first <= 0xdfU) {
            width = 2U;
        } else if (first >= 0xe0U && first <= 0xefU) {
            width = 3U;
        } else if (first >= 0xf0U && first <= 0xf4U) {
            width = 4U;
        } else {
            return false;
        }
        if (width > value.size() - index) {
            return false;
        }
        for (std::size_t continuation = 1U; continuation < width; ++continuation) {
            const auto byte = static_cast<unsigned char>(value[index + continuation]);
            if ((byte & 0xc0U) != 0x80U) {
                return false;
            }
        }
        const auto second = static_cast<unsigned char>(value[index + 1U]);
        if ((first == 0xe0U && second < 0xa0U) || (first == 0xedU && second >= 0xa0U)
            || (first == 0xf0U && second < 0x90U) || (first == 0xf4U && second >= 0x90U)) {
            return false;
        }
        index += width;
    }
    return true;
}

template <typename T>
[[nodiscard]] std::span<const T> checked_span(
    const T* const data,
    const std::uint64_t count,
    const std::uint64_t maximum = kMaxFamilyRows) {
    if (count == 0U) {
        if (data != nullptr) {
            fail(SA_ERR_INVALID_ARGUMENT, "empty ModelIR slice pointer must be null");
        }
        return {};
    }
    if (data == nullptr || count > maximum
        || count > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max() / sizeof(T))) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR slice pointer or count is invalid");
    }
    const auto size = static_cast<std::size_t>(count);
    const auto extent = size * sizeof(T);
    const auto address = reinterpret_cast<std::uintptr_t>(data);
    if (extent > 0U && address > std::numeric_limits<std::uintptr_t>::max() - (extent - 1U)) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR slice pointer extent overflows");
    }
    return {data, size};
}

[[nodiscard]] std::string copy_string(
    const sa_string_view_v1 view,
    const bool required,
    const std::uint64_t maximum = kMaxStringBytes) {
    if (view.length == 0U) {
        if (view.data != nullptr || required) {
            fail(SA_ERR_INVALID_ARGUMENT, "ModelIR string pointer or length is invalid");
        }
        return {};
    }
    if (view.data == nullptr || view.length > maximum
        || view.length > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR string pointer or length is invalid");
    }
    const auto size = static_cast<std::size_t>(view.length);
    const auto address = reinterpret_cast<std::uintptr_t>(view.data);
    if (address > std::numeric_limits<std::uintptr_t>::max() - (size - 1U)) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR string pointer extent overflows");
    }
    const std::string_view borrowed {view.data, size};
    if (!valid_utf8(borrowed)) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR string is not valid UTF-8");
    }
    return std::string {borrowed};
}

[[nodiscard]] std::optional<std::string> copy_optional_string(
    const sa_optional_string_view_v1& view) {
    require_boolean(view.is_present);
    require_zero(view.reserved);
    if (view.is_present == 0U) {
        if (view.value.data != nullptr || view.value.length != 0U) {
            fail(SA_ERR_INVALID_ARGUMENT, "absent ModelIR string carries storage");
        }
        return std::nullopt;
    }
    return copy_string(view.value, false);
}

[[nodiscard]] bool valid_hash(const std::string_view hash) noexcept {
    if (hash.size() != 71U || hash.substr(0U, 7U) != "sha256:") {
        return false;
    }
    return std::all_of(hash.begin() + 7, hash.end(), [](const char value) {
        return (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f');
    });
}

[[nodiscard]] Entity copy_entity(const sa_entity_identity_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    Entity entity;
    entity.id = copy_string(source.id, true);
    entity.index = source.index;
    entity.source_id = copy_optional_string(source.source_id);
    entity.extensions = copy_string(source.extensions_json, true);
    return entity;
}

template <typename T>
[[nodiscard]] std::vector<T> copy_trivial_slice(
    const T* const data,
    const std::uint64_t count,
    const std::uint64_t maximum = kMaxNestedRows) {
    const auto input = checked_span(data, count, maximum);
    return {input.begin(), input.end()};
}

[[nodiscard]] std::vector<std::string> copy_string_slice(
    const sa_string_view_v1* const data,
    const std::uint64_t count) {
    const auto input = checked_span(data, count, kMaxNestedRows);
    std::vector<std::string> output;
    output.reserve(input.size());
    for (const auto value : input) {
        output.push_back(copy_string(value, true));
    }
    return output;
}

[[nodiscard]] SourceUnits copy_source_units(const sa_source_units_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_zero(source.reserved);
    if (source.length < SA_LENGTH_UNIT_M || source.length > SA_LENGTH_UNIT_IN
        || source.force < SA_FORCE_UNIT_N || source.force > SA_FORCE_UNIT_KIP
        || source.mass < SA_MASS_UNIT_KG || source.mass > SA_MASS_UNIT_SLUG
        || source.time != SA_TIME_UNIT_S || source.rotation < SA_ROTATION_UNIT_RAD
        || source.rotation > SA_ROTATION_UNIT_DEG) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR source unit enum is unknown");
    }
    return {source.length, source.force, source.mass, source.time, source.rotation};
}

[[nodiscard]] UnitScales copy_unit_scales(const sa_unit_scales_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    return {
        source.length_to_m,
        source.force_to_n,
        source.mass_to_kg,
        source.time_to_s,
        source.rotation_to_rad,
    };
}

[[nodiscard]] Provenance copy_provenance(const sa_provenance_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_zero(source.reserved);
    if (source.source_format < SA_SOURCE_FORMAT_NEUTRAL_JSON
        || source.source_format > SA_SOURCE_FORMAT_GENERATED) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR source format enum is unknown");
    }
    auto source_sha256 = copy_string(source.source_sha256, true);
    if (!valid_hash(source_sha256)) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR provenance source_sha256 format is invalid");
    }
    Provenance provenance;
    provenance.source_format = source.source_format;
    provenance.source_ref = copy_string(source.source_ref, true);
    provenance.source_sha256 = std::move(source_sha256);
    provenance.normalizer_id = copy_string(source.normalizer_id, true);
    provenance.normalizer_version = copy_string(source.normalizer_version, true);
    provenance.source_units = copy_source_units(source.source_units);
    provenance.unit_scales = copy_unit_scales(source.unit_scales_to_si);
    provenance.extensions = copy_string(source.extensions_json, true);
    return provenance;
}

[[nodiscard]] Admissibility copy_admissibility(const sa_material_admissibility_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_boolean(source.is_present);
    require_zero(source.reserved);
    require_boolean(source.supports_unloading);
    require_boolean(source.supports_reversal);
    require_boolean(source.supports_cyclic);
    require_boolean(source.supports_tension);
    require_boolean(source.supports_compression);
    require_boolean(source.supports_multiaxial);
    if (source.is_present == 0U) {
        if (source.loading_domain.data != nullptr || source.loading_domain.length != 0U
            || source.supports_unloading != 0U || source.supports_reversal != 0U
            || source.supports_cyclic != 0U || source.supports_tension != 0U
            || source.supports_compression != 0U || source.supports_multiaxial != 0U) {
            fail(SA_ERR_INVALID_ARGUMENT, "absent material admissibility carries values");
        }
        return {};
    }
    Admissibility admissibility;
    admissibility.present = true;
    admissibility.loading_domain = copy_string(source.loading_domain, true);
    admissibility.supports = {
        source.supports_unloading != 0U,
        source.supports_reversal != 0U,
        source.supports_cyclic != 0U,
        source.supports_tension != 0U,
        source.supports_compression != 0U,
        source.supports_multiaxial != 0U,
    };
    return admissibility;
}

[[nodiscard]] Material copy_material(const sa_material_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_boolean(source.stateful);
    require_boolean(source.supports_trial_commit_rollback);
    require_zero(source.reserved);
    if (source.parameter_set_version != 1U) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR material parameter_set_version is unsupported");
    }

    MaterialParameters parameters;
    switch (source.law_id) {
    case SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC:
        parameters = source.parameters.linear;
        break;
    case SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL:
        require_boolean(source.parameters.steel.has_shear_modulus);
        require_zero(source.parameters.steel.reserved);
        parameters = source.parameters.steel;
        break;
    case SA_MATERIAL_ASYMMETRIC_CONCRETE_DAMAGE:
        parameters = source.parameters.concrete;
        break;
    default:
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR material law enum is unknown");
    }
    if (source.state_update_epoch < SA_MATERIAL_STATE_EPOCH_NONE
        || source.state_update_epoch > SA_MATERIAL_STATE_EPOCH_ACCEPTED_STEP) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR material state epoch enum is unknown");
    }
    const bool nonlinear = source.law_id != SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC;
    if ((source.stateful != 0U) != nonlinear
        || source.state_update_epoch
            != (nonlinear ? SA_MATERIAL_STATE_EPOCH_ACCEPTED_STEP : SA_MATERIAL_STATE_EPOCH_NONE)
        || source.supports_trial_commit_rollback == 0U) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR material state schema is inconsistent with its law");
    }
    Material material;
    material.identity = copy_entity(source.identity);
    material.law = source.law_id;
    material.parameter_set_version = source.parameter_set_version;
    material.parameters = parameters;
    material.stateful = source.stateful != 0U;
    material.state_update_epoch = source.state_update_epoch;
    material.supports_trial_commit_rollback = source.supports_trial_commit_rollback != 0U;
    material.admissibility = copy_admissibility(source.admissibility);
    return material;
}

[[nodiscard]] Section copy_section(const sa_section_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    if (source.parameter_set_version != 1U) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR section parameter_set_version is unsupported");
    }
    SectionParameters parameters;
    switch (source.family_id) {
    case SA_SECTION_FRAME_3D:
        parameters = source.parameters.frame;
        break;
    case SA_SECTION_TRUSS_3D:
        parameters = source.parameters.truss;
        break;
    case SA_SECTION_RECTANGULAR_RC_FIBER_2D:
        parameters = source.parameters.rc_fiber;
        break;
    default:
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR section family enum is unknown");
    }
    auto steel_material_id = copy_optional_string(source.steel_material_id);
    auto concrete_material_id = copy_optional_string(source.concrete_material_id);
    const bool rc_fiber = source.family_id == SA_SECTION_RECTANGULAR_RC_FIBER_2D;
    if (rc_fiber != (steel_material_id.has_value() && concrete_material_id.has_value())
        || (!rc_fiber && (steel_material_id.has_value() || concrete_material_id.has_value()))) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR section material references do not match its family");
    }
    Section section;
    section.identity = copy_entity(source.identity);
    section.family = source.family_id;
    section.parameter_set_version = source.parameter_set_version;
    section.parameters = parameters;
    section.steel_material_id = std::move(steel_material_id);
    section.concrete_material_id = std::move(concrete_material_id);
    return section;
}

[[nodiscard]] std::vector<std::uint32_t> copy_dofs(
    const sa_dof_v1* const data,
    const std::uint64_t count) {
    auto output = copy_trivial_slice(data, count, 6U);
    std::set<std::uint32_t> unique;
    for (const auto dof : output) {
        if (dof < SA_DOF_UX || dof > SA_DOF_RZ) {
            fail(SA_ERR_INVALID_ARGUMENT, "ModelIR DOF enum is unknown");
        }
        if (!unique.insert(dof).second) {
            fail(SA_ERR_SCHEMA_INVALID, "ModelIR DOF slice contains a duplicate");
        }
    }
    return output;
}

[[nodiscard]] Element copy_element(const sa_element_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_boolean(source.has_local_axis_rotation);
    require_boolean(source.has_integration_order);
    require_boolean(source.has_uniform_distributed_load_local);
    require_zero(source.reserved0);
    auto material_id = copy_optional_string(source.material_id);
    const bool frame3d = source.type == SA_ELEMENT_FRAME_3D;
    const bool truss3d = source.type == SA_ELEMENT_TRUSS_3D;
    const bool frame2d = source.type == SA_ELEMENT_FRAME_2D;
    if (!frame3d && !truss3d && !frame2d) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR element type enum is unknown");
    }
    const bool compatible =
        (source.formulation == SA_FORMULATION_EULER_BERNOULLI_3D && frame3d)
        || (source.formulation == SA_FORMULATION_LINEAR_TRUSS_3D && truss3d)
        || (source.formulation == SA_FORMULATION_STATEFUL_COROTATIONAL_TIMOSHENKO_FRAME3D
            && frame3d)
        || (source.formulation == SA_FORMULATION_STATEFUL_COROTATIONAL_RC_FIBER_FRAME2D
            && frame2d);
    if (!compatible) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR element formulation does not match its type");
    }
    if ((frame3d != (source.has_local_axis_rotation != 0U))
        || ((frame3d || truss3d) != material_id.has_value())
        || (frame2d != (source.has_integration_order != 0U))
        || (frame2d != (source.has_uniform_distributed_load_local != 0U))) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR element optional fields do not match its formulation");
    }
    auto releases_i = copy_dofs(source.releases_i, source.releases_i_count);
    auto releases_j = copy_dofs(source.releases_j, source.releases_j_count);
    if (truss3d && (!releases_i.empty() || !releases_j.empty())) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR truss element cannot carry releases");
    }
    std::optional<double> rotation;
    if (source.has_local_axis_rotation != 0U) {
        rotation = source.local_axis_rotation_rad;
    } else if (source.local_axis_rotation_rad != 0.0) {
        fail(SA_ERR_INVALID_ARGUMENT, "absent element local-axis rotation carries a value");
    }
    std::optional<std::uint64_t> integration_order;
    if (source.has_integration_order != 0U) {
        integration_order = source.integration_order;
    } else if (source.integration_order != 0U) {
        fail(SA_ERR_INVALID_ARGUMENT, "absent element integration order carries a value");
    }
    std::optional<std::array<double, 2>> uniform_load;
    if (source.has_uniform_distributed_load_local != 0U) {
        uniform_load = std::array<double, 2> {
            source.uniform_qx_n_per_m,
            source.uniform_qy_n_per_m,
        };
    } else if (source.uniform_qx_n_per_m != 0.0 || source.uniform_qy_n_per_m != 0.0) {
        fail(SA_ERR_INVALID_ARGUMENT, "absent element member load carries a value");
    }
    Element element;
    element.identity = copy_entity(source.identity);
    element.type = source.type;
    element.formulation = source.formulation;
    element.node_ids[0] = copy_string(source.node_ids[0], true);
    element.node_ids[1] = copy_string(source.node_ids[1], true);
    element.material_id = std::move(material_id);
    element.section_id = copy_string(source.section_id, true);
    element.local_axis_rotation_rad = rotation;
    element.offset_i = {
        source.offset_i_global_m[0],
        source.offset_i_global_m[1],
        source.offset_i_global_m[2],
    };
    element.offset_j = {
        source.offset_j_global_m[0],
        source.offset_j_global_m[1],
        source.offset_j_global_m[2],
    };
    element.releases_i = std::move(releases_i);
    element.releases_j = std::move(releases_j);
    element.integration_order = integration_order;
    element.uniform_load = uniform_load;
    return element;
}

[[nodiscard]] Constraint copy_constraint(const sa_constraint_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    auto dofs = copy_dofs(source.dofs, source.dof_count);
    const auto prescribed = checked_span(
        source.prescribed_values,
        source.prescribed_value_count,
        6U);
    std::vector<PrescribedValue> prescribed_values;
    prescribed_values.reserve(prescribed.size());
    std::set<std::uint32_t> unique;
    for (const auto& value : prescribed) {
        require_zero(value.reserved);
        if (value.dof < SA_DOF_UX || value.dof > SA_DOF_RZ) {
            fail(SA_ERR_INVALID_ARGUMENT, "ModelIR prescribed-value DOF enum is unknown");
        }
        if (!unique.insert(value.dof).second) {
            fail(SA_ERR_SCHEMA_INVALID, "ModelIR prescribed-value map contains a duplicate key");
        }
        prescribed_values.push_back({value.dof, value.value_si});
    }
    Constraint constraint;
    constraint.identity = copy_entity(source.identity);
    constraint.node_id = copy_string(source.node_id, true);
    constraint.dofs = std::move(dofs);
    constraint.prescribed_values = std::move(prescribed_values);
    return constraint;
}

[[nodiscard]] NodalLoad copy_nodal_load(const sa_nodal_load_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    NodalLoad load;
    load.identity = copy_entity(source.identity);
    load.node_id = copy_string(source.node_id, true);
    load.components = {
        source.components_si[0],
        source.components_si[1],
        source.components_si[2],
        source.components_si[3],
        source.components_si[4],
        source.components_si[5],
    };
    return load;
}

[[nodiscard]] LoadPattern copy_load_pattern(const sa_load_pattern_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_zero(source.reserved);
    if (source.analysis_type < SA_ANALYSIS_LINEAR_STATIC
        || source.analysis_type > SA_ANALYSIS_NONLINEAR_STATIC_DIRECT_DISPLACEMENT_CONTROL) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR analysis type enum is unknown");
    }
    const auto rows = checked_span(source.nodal_loads, source.nodal_load_count, kMaxNestedRows);
    std::vector<NodalLoad> nodal_loads;
    nodal_loads.reserve(rows.size());
    for (const auto& row : rows) {
        nodal_loads.push_back(copy_nodal_load(row));
    }
    LoadPattern pattern;
    pattern.identity = copy_entity(source.identity);
    pattern.analysis_type = source.analysis_type;
    pattern.self_weight = {source.self_weight[0], source.self_weight[1], source.self_weight[2]};
    pattern.nodal_loads = std::move(nodal_loads);
    return pattern;
}

[[nodiscard]] LoadCombination copy_load_combination(
    const sa_load_combination_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    const auto rows = checked_span(source.terms, source.term_count, kMaxNestedRows);
    std::vector<CombinationTerm> terms;
    terms.reserve(rows.size());
    for (const auto& row : rows) {
        require_header(row.abi_version, row.struct_size, sizeof(row));
        require_zero(row.reserved);
        if (row.ref_kind < SA_LOAD_REF_PATTERN || row.ref_kind > SA_LOAD_REF_COMBINATION) {
            fail(SA_ERR_INVALID_ARGUMENT, "ModelIR load reference kind enum is unknown");
        }
        terms.push_back({copy_string(row.ref_id, true), row.ref_kind, row.factor});
    }
    LoadCombination combination;
    combination.identity = copy_entity(source.identity);
    combination.terms = std::move(terms);
    return combination;
}

[[nodiscard]] TimeFunction copy_time_function(const sa_time_function_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    TimeFunction function;
    function.id = copy_string(source.id, true);
    function.index = source.index;
    function.points = copy_trivial_slice(source.points, source.point_count, kMaxNestedRows);
    function.extensions = copy_string(source.extensions_json, true);
    return function;
}

[[nodiscard]] ConstructionStage copy_construction_stage(
    const sa_construction_stage_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    ConstructionStage stage;
    stage.id = copy_string(source.id, true);
    stage.index = source.index;
    stage.active_element_ids =
        copy_string_slice(source.active_element_ids, source.active_element_id_count);
    stage.active_constraint_ids =
        copy_string_slice(source.active_constraint_ids, source.active_constraint_id_count);
    stage.load_pattern_ids = copy_string_slice(source.load_pattern_ids, source.load_pattern_id_count);
    stage.extensions = copy_string(source.extensions_json, true);
    return stage;
}

[[nodiscard]] RoundtripRow copy_roundtrip_row(const sa_roundtrip_row_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_zero(source.reserved);
    require_zero(source.reserved1);
    if (source.entity_kind < SA_MODEL_IR_ENTITY_NODE
        || source.entity_kind > SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE
        || source.mapping_status < SA_ROUNDTRIP_EXACT
        || source.mapping_status > SA_ROUNDTRIP_UNSUPPORTED) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR roundtrip enum is unknown");
    }
    RoundtripRow row;
    row.source_entity_id = copy_string(source.source_entity_id, true);
    row.entity_kind = source.entity_kind;
    row.model_ir_entity_id = copy_string(source.model_ir_entity_id, true);
    row.mapping_status = source.mapping_status;
    row.extensions = copy_string(source.extensions_json, true);
    return row;
}

[[nodiscard]] UnsupportedFeature copy_unsupported_feature(
    const sa_unsupported_feature_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    require_boolean(source.blocking);
    if (source.disposition < SA_UNSUPPORTED_BLOCKED
        || source.disposition > SA_UNSUPPORTED_PRESERVED_ONLY) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR unsupported disposition enum is unknown");
    }
    UnsupportedFeature feature;
    feature.feature_id = copy_string(source.feature_id, true);
    feature.kind = copy_string(source.kind, true);
    feature.source_entity_id = copy_optional_string(source.source_entity_id);
    feature.disposition = source.disposition;
    feature.blocking = source.blocking != 0U;
    feature.detail = copy_string(source.detail, true);
    feature.extensions = copy_string(source.extensions_json, true);
    return feature;
}

template <typename Source, typename Target, typename Copier>
[[nodiscard]] std::vector<Target> copy_family(
    const Source* const data,
    const std::uint64_t count,
    Copier copier) {
    const auto input = checked_span(data, count);
    std::vector<Target> output;
    output.reserve(input.size());
    for (const auto& row : input) {
        output.push_back(copier(row));
    }
    return output;
}

[[nodiscard]] OwnedModel copy_model(const sa_model_ir_descriptor_v1& source) {
    require_header(source.abi_version, source.struct_size, sizeof(source));
    if (source.flags != 0U || std::any_of(std::begin(source.reserved), std::end(source.reserved),
                                 [](const auto value) { return value != 0U; })) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR root flags or reserved fields are not zero");
    }
    if (source.capability_profile < SA_MODEL_IR_PROFILE_GENERAL
        || source.capability_profile
            > SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR capability profile enum is unknown");
    }
    require_zero(source.reserved0);

    const auto canonical_units = copy_source_units(source.canonical_units);
    if (canonical_units.length != SA_LENGTH_UNIT_M || canonical_units.force != SA_FORCE_UNIT_N
        || canonical_units.mass != SA_MASS_UNIT_KG || canonical_units.time != SA_TIME_UNIT_S
        || canonical_units.rotation != SA_ROTATION_UNIT_RAD) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR canonical unit constants are invalid");
    }
    require_header(
        source.coordinate_system.abi_version,
        source.coordinate_system.struct_size,
        sizeof(source.coordinate_system));
    require_boolean(source.coordinate_system.is_global);
    require_boolean(source.coordinate_system.axis_order_xyz);
    require_boolean(source.coordinate_system.up_axis_z);
    require_boolean(source.coordinate_system.right_handed);
    if (source.coordinate_system.is_global == 0U || source.coordinate_system.axis_order_xyz == 0U
        || source.coordinate_system.up_axis_z == 0U
        || source.coordinate_system.right_handed == 0U) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR coordinate-system constants are invalid");
    }
    auto dof_components = copy_dofs(source.dof_components, source.dof_component_count);
    constexpr std::array<std::uint32_t, 6> kCanonicalDofs {
        SA_DOF_UX,
        SA_DOF_UY,
        SA_DOF_UZ,
        SA_DOF_RX,
        SA_DOF_RY,
        SA_DOF_RZ,
    };
    if (!std::equal(dof_components.begin(), dof_components.end(), kCanonicalDofs.begin(),
            kCanonicalDofs.end())) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR DOF components are not in canonical order");
    }

    auto schema_version = copy_string(source.schema_version, true);
    if (schema_version != "structural-analysis-model-ir.v2") {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR schema_version is unsupported");
    }
    auto canonical_json = copy_string(source.canonical_json, true, kMaxSnapshotBytes);
    auto content_hash = copy_string(source.content_hash, true);
    auto semantic_hash = copy_string(source.semantic_hash, true);
    auto provenance_hash = copy_string(source.provenance_hash, true);
    if (!valid_hash(content_hash) || !valid_hash(semantic_hash) || !valid_hash(provenance_hash)) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR identity hash format is invalid");
    }
    if (content_hash != "sha256:" + sha256_hex(canonical_json)) {
        fail(SA_ERR_SCHEMA_INVALID, "ModelIR canonical snapshot does not match content_hash");
    }

    OwnedModel model;
    model.schema_version = std::move(schema_version);
    model.model_id = copy_string(source.model_id, true);
    model.capability_profile = source.capability_profile;
    model.canonical_units = canonical_units;
    model.coordinate_origin = {
        source.coordinate_system.origin_m[0],
        source.coordinate_system.origin_m[1],
        source.coordinate_system.origin_m[2],
    };
    model.dof_components = std::move(dof_components);
    model.provenance = copy_provenance(source.provenance);
    model.nodes = copy_family<sa_node_descriptor_v1, Node>(
        source.nodes,
        source.node_count,
        [](const auto& row) {
            require_header(row.abi_version, row.struct_size, sizeof(row));
            return Node {
                copy_entity(row.identity),
                {row.coordinates_m[0], row.coordinates_m[1], row.coordinates_m[2]},
            };
        });
    model.materials = copy_family<sa_material_descriptor_v1, Material>(
        source.materials, source.material_count, copy_material);
    model.sections = copy_family<sa_section_descriptor_v1, Section>(
        source.sections, source.section_count, copy_section);
    model.elements = copy_family<sa_element_descriptor_v1, Element>(
        source.elements, source.element_count, copy_element);
    model.constraints = copy_family<sa_constraint_descriptor_v1, Constraint>(
        source.constraints, source.constraint_count, copy_constraint);
    model.load_patterns = copy_family<sa_load_pattern_descriptor_v1, LoadPattern>(
        source.load_patterns, source.load_pattern_count, copy_load_pattern);
    model.load_combinations = copy_family<sa_load_combination_descriptor_v1, LoadCombination>(
        source.load_combinations, source.load_combination_count, copy_load_combination);
    model.time_functions = copy_family<sa_time_function_descriptor_v1, TimeFunction>(
        source.time_functions, source.time_function_count, copy_time_function);
    model.construction_stages =
        copy_family<sa_construction_stage_descriptor_v1, ConstructionStage>(
            source.construction_stages,
            source.construction_stage_count,
            copy_construction_stage);
    model.roundtrip_rows = copy_family<sa_roundtrip_row_descriptor_v1, RoundtripRow>(
        source.roundtrip_rows, source.roundtrip_row_count, copy_roundtrip_row);
    model.unsupported_features =
        copy_family<sa_unsupported_feature_descriptor_v1, UnsupportedFeature>(
            source.unsupported_features,
            source.unsupported_feature_count,
            copy_unsupported_feature);
    model.extensions = copy_string(source.extensions_json, true);
    model.canonical_json = std::move(canonical_json);
    model.content_hash = std::move(content_hash);
    model.semantic_hash = std::move(semantic_hash);
    model.provenance_hash = std::move(provenance_hash);
    return model;
}

void add_finite_issue(
    std::vector<Issue>& issues,
    const double value,
    const std::string& path) {
    if (!std::isfinite(value)) {
        issues.push_back({
            "non_finite_number",
            path,
            "Numbers must be finite and representable as binary64 values.",
        });
    }
}

[[nodiscard]] std::vector<Issue> finite_issues(const OwnedModel& model) {
    std::vector<Issue> issues;
    for (std::size_t axis = 0U; axis < model.coordinate_origin.size(); ++axis) {
        add_finite_issue(
            issues,
            model.coordinate_origin[axis],
            "/coordinate_system/origin_m/" + std::to_string(axis));
    }
    const std::array<std::pair<double, const char*>, 5> scales {{
        {model.provenance.unit_scales.length_to_m, "length_to_m"},
        {model.provenance.unit_scales.force_to_n, "force_to_n"},
        {model.provenance.unit_scales.mass_to_kg, "mass_to_kg"},
        {model.provenance.unit_scales.time_to_s, "time_to_s"},
        {model.provenance.unit_scales.rotation_to_rad, "rotation_to_rad"},
    }};
    for (const auto& [value, name] : scales) {
        add_finite_issue(
            issues,
            value,
            std::string {"/provenance/unit_scales_to_si/"} + name);
    }
    for (std::size_t index = 0U; index < model.nodes.size(); ++index) {
        for (std::size_t axis = 0U; axis < 3U; ++axis) {
            add_finite_issue(
                issues,
                model.nodes[index].coordinates[axis],
                "/nodes/" + std::to_string(index) + "/coordinates_m/" + std::to_string(axis));
        }
    }
    for (std::size_t index = 0U; index < model.materials.size(); ++index) {
        const auto base = "/materials/" + std::to_string(index) + "/parameters/";
        const auto& material = model.materials[index];
        if (const auto* values = std::get_if<sa_linear_material_parameters_v1>(
                &material.parameters)) {
            add_finite_issue(issues, values->elastic_modulus_pa, base + "elastic_modulus_pa");
            add_finite_issue(issues, values->poisson_ratio, base + "poisson_ratio");
            add_finite_issue(issues, values->density_kg_m3, base + "density_kg_m3");
        } else if (const auto* values = std::get_if<sa_steel_material_parameters_v1>(
                       &material.parameters)) {
            add_finite_issue(issues, values->elastic_modulus_pa, base + "elastic_modulus_pa");
            if (values->has_shear_modulus != 0U) {
                add_finite_issue(issues, values->shear_modulus_pa, base + "shear_modulus_pa");
            }
            add_finite_issue(issues, values->yield_stress_pa, base + "yield_stress_pa");
            add_finite_issue(
                issues,
                values->isotropic_hardening_modulus_pa,
                base + "isotropic_hardening_modulus_pa");
            add_finite_issue(
                issues,
                values->kinematic_hardening_modulus_pa,
                base + "kinematic_hardening_modulus_pa");
            add_finite_issue(issues, values->yield_tolerance_pa, base + "yield_tolerance_pa");
        } else {
            const auto& concrete_values = std::get<sa_concrete_material_parameters_v1>(
                material.parameters);
            add_finite_issue(
                issues, concrete_values.elastic_modulus_pa, base + "elastic_modulus_pa");
            add_finite_issue(
                issues, concrete_values.tensile_strength_pa, base + "tensile_strength_pa");
            add_finite_issue(
                issues,
                concrete_values.compressive_strength_pa,
                base + "compressive_strength_pa");
            add_finite_issue(
                issues,
                concrete_values.tensile_softening_rate,
                base + "tensile_softening_rate");
            add_finite_issue(
                issues,
                concrete_values.compressive_softening_rate,
                base + "compressive_softening_rate");
            add_finite_issue(
                issues, concrete_values.history_tolerance, base + "history_tolerance");
        }
    }
    for (std::size_t index = 0U; index < model.sections.size(); ++index) {
        const auto base = "/sections/" + std::to_string(index) + "/parameters/";
        const auto& section = model.sections[index];
        if (const auto* values = std::get_if<sa_frame_section_parameters_v1>(
                &section.parameters)) {
            const std::array<std::pair<double, const char*>, 6> fields {{
                {values->area_m2, "area_m2"},
                {values->iy_m4, "iy_m4"},
                {values->iz_m4, "iz_m4"},
                {values->torsional_constant_m4, "torsional_constant_m4"},
                {values->shear_area_y_m2, "shear_area_y_m2"},
                {values->shear_area_z_m2, "shear_area_z_m2"},
            }};
            for (const auto& [value, name] : fields) {
                add_finite_issue(issues, value, base + name);
            }
        } else if (const auto* values = std::get_if<sa_truss_section_parameters_v1>(
                       &section.parameters)) {
            add_finite_issue(issues, values->area_m2, base + "area_m2");
        } else {
            const auto& rc_values = std::get<sa_rc_fiber_section_parameters_v1>(
                section.parameters);
            add_finite_issue(issues, rc_values.width_m, base + "width_m");
            add_finite_issue(issues, rc_values.depth_m, base + "depth_m");
            add_finite_issue(issues, rc_values.cover_m, base + "cover_m");
            add_finite_issue(issues, rc_values.bar_area_m2, base + "bar_area_m2");
        }
    }
    for (std::size_t index = 0U; index < model.elements.size(); ++index) {
        const auto base = "/elements/" + std::to_string(index);
        const auto& element = model.elements[index];
        if (element.local_axis_rotation_rad.has_value()) {
            add_finite_issue(
                issues, *element.local_axis_rotation_rad, base + "/local_axis_rotation_rad");
        }
        for (std::size_t axis = 0U; axis < 3U; ++axis) {
            add_finite_issue(
                issues,
                element.offset_i[axis],
                base + "/offsets/i_global_m/" + std::to_string(axis));
            add_finite_issue(
                issues,
                element.offset_j[axis],
                base + "/offsets/j_global_m/" + std::to_string(axis));
        }
        if (element.uniform_load.has_value()) {
            add_finite_issue(
                issues,
                (*element.uniform_load)[0],
                base + "/uniform_distributed_load_local/qx_n_per_m");
            add_finite_issue(
                issues,
                (*element.uniform_load)[1],
                base + "/uniform_distributed_load_local/qy_n_per_m");
        }
    }
    for (std::size_t index = 0U; index < model.constraints.size(); ++index) {
        const auto base = "/constraints/" + std::to_string(index) + "/prescribed_values_si/";
        for (const auto& value : model.constraints[index].prescribed_values) {
            add_finite_issue(issues, value.value, base + std::to_string(value.dof));
        }
    }
    for (std::size_t pattern_index = 0U; pattern_index < model.load_patterns.size();
         ++pattern_index) {
        const auto& pattern = model.load_patterns[pattern_index];
        const auto base = "/load_patterns/" + std::to_string(pattern_index);
        for (std::size_t axis = 0U; axis < 3U; ++axis) {
            add_finite_issue(
                issues,
                pattern.self_weight[axis],
                base + "/self_weight/" + std::to_string(axis));
        }
        for (std::size_t load_index = 0U; load_index < pattern.nodal_loads.size(); ++load_index) {
            for (std::size_t component = 0U; component < 6U; ++component) {
                add_finite_issue(
                    issues,
                    pattern.nodal_loads[load_index].components[component],
                    base + "/nodal_loads/" + std::to_string(load_index)
                        + "/components_si/" + std::to_string(component));
            }
        }
    }
    for (std::size_t index = 0U; index < model.load_combinations.size(); ++index) {
        for (std::size_t term = 0U; term < model.load_combinations[index].terms.size(); ++term) {
            add_finite_issue(
                issues,
                model.load_combinations[index].terms[term].factor,
                "/load_combinations/" + std::to_string(index) + "/terms/"
                    + std::to_string(term) + "/factor");
        }
    }
    for (std::size_t index = 0U; index < model.time_functions.size(); ++index) {
        for (std::size_t point = 0U; point < model.time_functions[index].points.size(); ++point) {
            add_finite_issue(
                issues,
                model.time_functions[index].points[point].time,
                "/time_functions/" + std::to_string(index) + "/points/"
                    + std::to_string(point) + "/0");
            add_finite_issue(
                issues,
                model.time_functions[index].points[point].value,
                "/time_functions/" + std::to_string(index) + "/points/"
                    + std::to_string(point) + "/1");
        }
    }
    return issues;
}

[[nodiscard]] bool close_scale(const double actual, const double expected) noexcept {
    return std::abs(actual - expected)
        <= std::max(1.0e-15, 1.0e-12 * std::max(std::abs(actual), std::abs(expected)));
}

void add_unit_scale_issues(const OwnedModel& model, std::vector<Issue>& issues) {
    const auto& units = model.provenance.source_units;
    const auto& scales = model.provenance.unit_scales;
    constexpr std::array<double, 5> kLength {1.0, 1.0e-3, 1.0e-2, 0.3048, 0.0254};
    constexpr std::array<double, 5> kForce {
        1.0,
        1.0e3,
        1.0e6,
        4.4482216152605,
        4448.2216152605,
    };
    constexpr std::array<double, 3> kMass {1.0, 1.0e3, 14.593902937206};
    constexpr std::array<double, 1> kTime {1.0};
    constexpr std::array<double, 2> kRotation {1.0, 0.017453292519943295};
    const std::array<std::tuple<double, double, const char*>, 5> values {{
        {scales.length_to_m, kLength[units.length - 1U], "length_to_m"},
        {scales.force_to_n, kForce[units.force - 1U], "force_to_n"},
        {scales.mass_to_kg, kMass[units.mass - 1U], "mass_to_kg"},
        {scales.time_to_s, kTime[units.time - 1U], "time_to_s"},
        {scales.rotation_to_rad, kRotation[units.rotation - 1U], "rotation_to_rad"},
    }};
    for (const auto& [actual, expected, name] : values) {
        if (!close_scale(actual, expected)) {
            issues.push_back({
                "unit_scale_mismatch",
                std::string {"/provenance/unit_scales_to_si/"} + name,
                "Source unit and SI conversion scale do not agree.",
            });
        }
    }
}

template <typename T, typename Identity>
void add_indexed_family_issues(
    const std::vector<T>& rows,
    const std::string& family,
    Identity identity,
    std::vector<Issue>& issues) {
    std::unordered_set<std::string> ids;
    std::unordered_set<std::uint64_t> indices;
    bool duplicate_id = false;
    bool duplicate_index = false;
    bool canonical_order = true;
    for (std::size_t index = 0U; index < rows.size(); ++index) {
        const auto& row = identity(rows[index]);
        duplicate_id = !ids.insert(row.id).second || duplicate_id;
        duplicate_index = !indices.insert(row.index).second || duplicate_index;
        canonical_order = row.index == static_cast<std::uint64_t>(index) && canonical_order;
    }
    if (duplicate_id) {
        issues.push_back({"duplicate_id", "/" + family, family + " id values must be unique."});
    }
    if (duplicate_index) {
        issues.push_back(
            {"duplicate_index", "/" + family, family + " indices must be unique."});
    }
    if (!canonical_order) {
        issues.push_back({
            "noncanonical_index_order",
            "/" + family,
            family + " indices must be contiguous and match array order.",
        });
    }
}

template <typename T>
[[nodiscard]] std::unordered_set<std::string> entity_ids(const std::vector<T>& rows) {
    std::unordered_set<std::string> ids;
    ids.reserve(rows.size());
    for (const auto& row : rows) {
        ids.insert(row.identity.id);
    }
    return ids;
}

void add_missing_reference(
    std::vector<Issue>& issues,
    std::string path,
    const char* const kind,
    const std::string& reference) {
    issues.push_back({
        "dangling_reference",
        std::move(path),
        std::string {"Unknown "} + kind + " reference: " + reference,
    });
}

[[nodiscard]] std::string dof_name(const std::uint32_t dof) {
    constexpr std::array<const char*, 6> kNames {"UX", "UY", "UZ", "RX", "RY", "RZ"};
    return kNames[dof - 1U];
}

void add_load_combination_issues(
    const OwnedModel& model,
    const std::unordered_set<std::string>& pattern_ids,
    const std::unordered_set<std::string>& combination_ids,
    std::vector<Issue>& issues) {
    std::map<std::string, std::vector<std::string>> graph;
    for (const auto& combination : model.load_combinations) {
        graph.emplace(combination.identity.id, std::vector<std::string> {});
    }
    for (std::size_t index = 0U; index < model.load_combinations.size(); ++index) {
        const auto& combination = model.load_combinations[index];
        for (std::size_t term_index = 0U; term_index < combination.terms.size(); ++term_index) {
            const auto& term = combination.terms[term_index];
            const auto path = "/load_combinations/" + std::to_string(index) + "/terms/"
                + std::to_string(term_index) + "/ref_id";
            if (term.ref_kind == SA_LOAD_REF_PATTERN) {
                if (!pattern_ids.contains(term.ref_id)) {
                    add_missing_reference(issues, path, "load_pattern", term.ref_id);
                }
            } else if (!combination_ids.contains(term.ref_id)) {
                add_missing_reference(issues, path, "load_combination", term.ref_id);
            } else {
                graph[combination.identity.id].push_back(term.ref_id);
            }
        }
    }

    std::map<std::string, std::uint32_t> state;
    for (const auto& [id, unused] : graph) {
        static_cast<void>(unused);
        state[id] = 0U;
    }
    for (const auto& [root, unused] : graph) {
        static_cast<void>(unused);
        if (state[root] != 0U) {
            continue;
        }
        std::vector<std::pair<std::string, std::size_t>> stack {{root, 0U}};
        std::vector<std::string> trail;
        std::map<std::string, std::size_t> positions;
        while (!stack.empty()) {
            auto& [node, child_index] = stack.back();
            if (state[node] == 0U) {
                state[node] = 1U;
                positions[node] = trail.size();
                trail.push_back(node);
            }
            const auto& children = graph[node];
            if (child_index < children.size()) {
                const auto child = children[child_index];
                ++child_index;
                if (state[child] == 0U) {
                    stack.emplace_back(child, 0U);
                } else if (state[child] == 1U) {
                    std::string detail = "Load-combination graph contains a cycle: ";
                    const auto start = positions[child];
                    for (std::size_t trail_index = start; trail_index < trail.size();
                         ++trail_index) {
                        if (trail_index != start) {
                            detail += " -> ";
                        }
                        detail += trail[trail_index];
                    }
                    detail += " -> " + child;
                    issues.push_back({"load_combination_cycle", "/load_combinations", detail});
                    return;
                }
                continue;
            }
            state[node] = 2U;
            positions.erase(node);
            trail.pop_back();
            stack.pop_back();
        }
    }
}

template <typename T, typename Id, typename Index>
void add_plain_indexed_family_issues(
    const std::vector<T>& rows,
    const std::string& family,
    Id id,
    Index row_index,
    std::vector<Issue>& issues) {
    std::unordered_set<std::string> ids;
    std::unordered_set<std::uint64_t> indices;
    bool duplicate_id = false;
    bool duplicate_index = false;
    bool canonical_order = true;
    for (std::size_t index = 0U; index < rows.size(); ++index) {
        duplicate_id = !ids.insert(id(rows[index])).second || duplicate_id;
        const auto value = row_index(rows[index]);
        duplicate_index = !indices.insert(value).second || duplicate_index;
        canonical_order = value == static_cast<std::uint64_t>(index) && canonical_order;
    }
    if (duplicate_id) {
        issues.push_back({"duplicate_id", "/" + family, family + " id values must be unique."});
    }
    if (duplicate_index) {
        issues.push_back(
            {"duplicate_index", "/" + family, family + " indices must be unique."});
    }
    if (!canonical_order) {
        issues.push_back({
            "noncanonical_index_order",
            "/" + family,
            family + " indices must be contiguous and match array order.",
        });
    }
}

void add_bounded_planar_issues(
    const OwnedModel& model,
    const std::unordered_set<std::string>& node_ids,
    const std::unordered_map<std::string, const Material*>& materials,
    const std::unordered_map<std::string, const Section*>& sections,
    const std::map<std::pair<std::string, std::uint32_t>, double>& constrained_dofs,
    std::vector<Issue>& issues) {
    const std::set<std::uint32_t> active_components {SA_DOF_UX, SA_DOF_UY, SA_DOF_RZ};
    const std::set<std::uint32_t> inactive_components {SA_DOF_UZ, SA_DOF_RX, SA_DOF_RY};
    std::set<std::string> referenced_materials;
    for (std::size_t index = 0U; index < model.sections.size(); ++index) {
        const auto& section = model.sections[index];
        const auto base = "/sections/" + std::to_string(index);
        if (!section.steel_material_id.has_value() || !section.concrete_material_id.has_value()) {
            continue;
        }
        referenced_materials.insert(*section.steel_material_id);
        referenced_materials.insert(*section.concrete_material_id);
        const auto steel = materials.find(*section.steel_material_id);
        if (steel == materials.end()
            || steel->second->law != SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL) {
            issues.push_back({
                "bounded_planar_section_steel_material_invalid",
                base + "/steel_material_id",
                "Section steel material must reference the bounded bilinear steel law.",
            });
        }
        const auto concrete = materials.find(*section.concrete_material_id);
        if (concrete == materials.end()
            || concrete->second->law != SA_MATERIAL_ASYMMETRIC_CONCRETE_DAMAGE) {
            issues.push_back({
                "bounded_planar_section_concrete_material_invalid",
                base + "/concrete_material_id",
                "Section concrete material must reference the bounded asymmetric concrete law.",
            });
        }
        if (const auto* parameters = std::get_if<sa_rc_fiber_section_parameters_v1>(
                &section.parameters);
            parameters != nullptr
            && 2.0 * parameters->cover_m >= std::min(parameters->width_m, parameters->depth_m)) {
            issues.push_back({
                "bounded_planar_section_cover_invalid",
                base + "/parameters/cover_m",
                "Twice the cover must be smaller than both section dimensions.",
            });
        }
    }
    std::set<std::string> material_ids;
    for (const auto& [id, unused] : materials) {
        static_cast<void>(unused);
        material_ids.insert(id);
    }
    if (referenced_materials != material_ids) {
        issues.push_back({
            "bounded_planar_unused_material",
            "/materials",
            "Every bounded planar material must be referenced by a section.",
        });
    }

    std::set<std::pair<double, double>> xy_coordinates;
    bool duplicate_coordinates = false;
    for (std::size_t index = 0U; index < model.nodes.size(); ++index) {
        const auto& coordinates = model.nodes[index].coordinates;
        if (coordinates[2] != 0.0) {
            issues.push_back({
                "bounded_planar_node_out_of_plane",
                "/nodes/" + std::to_string(index) + "/coordinates_m/2",
                "Bounded planar nodes require Z=0.",
            });
        }
        duplicate_coordinates = !xy_coordinates.emplace(coordinates[0], coordinates[1]).second
            || duplicate_coordinates;
    }
    if (duplicate_coordinates) {
        issues.push_back({
            "bounded_planar_node_coordinate_duplicate",
            "/nodes",
            "Bounded planar node XY coordinates must be unique.",
        });
    }

    std::map<std::string, std::set<std::string>> graph;
    for (const auto& id : node_ids) {
        graph.emplace(id, std::set<std::string> {});
    }
    std::set<std::pair<std::string, std::string>> member_pairs;
    std::set<std::string> referenced_sections;
    bool member_load_present = false;
    for (std::size_t index = 0U; index < model.elements.size(); ++index) {
        const auto& element = model.elements[index];
        const auto base = "/elements/" + std::to_string(index);
        auto pair = std::make_pair(element.node_ids[0], element.node_ids[1]);
        if (pair.second < pair.first) {
            std::swap(pair.first, pair.second);
        }
        if (!member_pairs.insert(pair).second) {
            issues.push_back({
                "bounded_planar_parallel_member_unsupported",
                base + "/node_ids",
                "The bounded profile does not support parallel members.",
            });
        }
        if (graph.contains(element.node_ids[0]) && graph.contains(element.node_ids[1])) {
            graph[element.node_ids[0]].insert(element.node_ids[1]);
            graph[element.node_ids[1]].insert(element.node_ids[0]);
        }
        referenced_sections.insert(element.section_id);
        if (element.offset_i[2] != 0.0 || element.offset_j[2] != 0.0) {
            issues.push_back({
                "bounded_planar_offset_out_of_plane",
                base + "/offsets",
                "Bounded planar rigid offsets require zero global Z components.",
            });
        }
        const auto unsupported_release = [](const std::vector<std::uint32_t>& releases) {
            return std::any_of(releases.begin(), releases.end(),
                [](const auto dof) { return dof != SA_DOF_RZ; });
        };
        if (unsupported_release(element.releases_i) || unsupported_release(element.releases_j)) {
            issues.push_back({
                "bounded_planar_release_unsupported",
                base + "/releases",
                "Only an optional RZ release at either member end is supported.",
            });
        }
        if (element.uniform_load.has_value()) {
            member_load_present = member_load_present || (*element.uniform_load)[0] != 0.0
                || (*element.uniform_load)[1] != 0.0;
        }
    }
    std::set<std::string> section_ids;
    for (const auto& [id, unused] : sections) {
        static_cast<void>(unused);
        section_ids.insert(id);
    }
    if (referenced_sections != section_ids) {
        issues.push_back({
            "bounded_planar_unused_section",
            "/sections",
            "Every bounded planar section must be referenced by a member.",
        });
    }
    if (!node_ids.empty()) {
        const auto start = *std::min_element(node_ids.begin(), node_ids.end());
        std::set<std::string> visited {start};
        std::vector<std::string> pending {start};
        while (!pending.empty()) {
            auto current = std::move(pending.back());
            pending.pop_back();
            for (const auto& neighbor : graph[current]) {
                if (visited.insert(neighbor).second) {
                    pending.push_back(neighbor);
                }
            }
        }
        if (visited.size() != node_ids.size()) {
            issues.push_back({
                "bounded_planar_graph_disconnected",
                "/elements",
                "The bounded planar member graph must be connected.",
            });
        }
    }

    std::optional<std::pair<std::string, std::uint32_t>> inactive_missing;
    for (const auto& node_id : node_ids) {
        for (const auto dof : inactive_components) {
            if (!constrained_dofs.contains({node_id, dof})) {
                const auto candidate = std::make_pair(node_id, dof);
                if (!inactive_missing.has_value() || candidate < *inactive_missing) {
                    inactive_missing = candidate;
                }
            }
        }
    }
    if (inactive_missing.has_value()) {
        issues.push_back({
            "bounded_planar_inactive_dof_unrestrained",
            "/constraints",
            "Node " + inactive_missing->first + " inactive component "
                + dof_name(inactive_missing->second) + " must be restrained.",
        });
    }
    bool active_support_present = false;
    bool prescribed_present = false;
    for (const auto& [key, value] : constrained_dofs) {
        const auto& [node_id, dof] = key;
        if (inactive_components.contains(dof) && value != 0.0) {
            issues.push_back({
                "bounded_planar_inactive_dof_prescribed_nonzero",
                "/constraints",
                "Node " + node_id + " inactive component " + dof_name(dof)
                    + " must be fixed at zero.",
            });
        }
        active_support_present = active_support_present || active_components.contains(dof);
        prescribed_present = prescribed_present || (active_components.contains(dof) && value != 0.0);
    }
    if (!active_support_present) {
        issues.push_back({
            "bounded_planar_active_support_missing",
            "/constraints",
            "At least one active UX, UY, or RZ support is required.",
        });
    }

    bool nodal_load_present = false;
    if (!model.load_patterns.empty()) {
        std::set<std::string> seen_load_nodes;
        const auto& pattern = model.load_patterns.front();
        for (std::size_t index = 0U; index < pattern.nodal_loads.size(); ++index) {
            const auto& load = pattern.nodal_loads[index];
            const auto base = "/load_patterns/0/nodal_loads/" + std::to_string(index);
            if (!seen_load_nodes.insert(load.node_id).second) {
                issues.push_back({
                    "bounded_planar_duplicate_nodal_load",
                    base + "/node_id",
                    "Use at most one bounded planar nodal-load row per node.",
                });
            }
            if (load.components[2] != 0.0 || load.components[3] != 0.0
                || load.components[4] != 0.0) {
                issues.push_back({
                    "bounded_planar_load_out_of_plane",
                    base + "/components_si",
                    "Only in-plane FX, FY, and MZ nodal loads are supported.",
                });
            }
            const bool in_plane = load.components[0] != 0.0 || load.components[1] != 0.0
                || load.components[5] != 0.0;
            if (!in_plane) {
                issues.push_back({
                    "bounded_planar_zero_nodal_load",
                    base + "/components_si",
                    "A declared bounded planar nodal-load row must be nonzero.",
                });
            }
            nodal_load_present = nodal_load_present || in_plane;
        }
    }
    if (!nodal_load_present && !member_load_present && !prescribed_present) {
        issues.push_back({
            "bounded_planar_load_missing",
            "/load_patterns/0",
            "At least one nodal, member, or prescribed-displacement load is required.",
        });
    }
}

[[nodiscard]] std::size_t matrix_rank(std::vector<std::array<double, 6>> rows) {
    if (rows.empty()) {
        return 0U;
    }
    double maximum = 0.0;
    for (const auto& row : rows) {
        for (const auto value : row) {
            maximum = std::max(maximum, std::abs(value));
        }
    }
    const auto dimension = static_cast<double>(std::max<std::size_t>(rows.size(), 6U));
    const auto tolerance = dimension * std::numeric_limits<double>::epsilon()
        * std::max(maximum, 1.0);
    std::size_t rank = 0U;
    for (std::size_t column = 0U; column < 6U && rank < rows.size(); ++column) {
        std::size_t pivot = rank;
        for (std::size_t candidate = rank + 1U; candidate < rows.size(); ++candidate) {
            if (std::abs(rows[candidate][column]) > std::abs(rows[pivot][column])) {
                pivot = candidate;
            }
        }
        if (std::abs(rows[pivot][column]) <= tolerance) {
            continue;
        }
        std::swap(rows[pivot], rows[rank]);
        const auto divisor = rows[rank][column];
        for (std::size_t value = column; value < 6U; ++value) {
            rows[rank][value] /= divisor;
        }
        for (std::size_t candidate = 0U; candidate < rows.size(); ++candidate) {
            if (candidate == rank) {
                continue;
            }
            const auto factor = rows[candidate][column];
            for (std::size_t value = column; value < 6U; ++value) {
                rows[candidate][value] -= factor * rows[rank][value];
            }
        }
        ++rank;
    }
    return rank;
}

[[nodiscard]] bool add_bounded_frame3d_numeric_issues(
    const OwnedModel& model,
    std::vector<Issue>& issues) {
    const auto initial_size = issues.size();
    for (std::size_t index = 0U; index < model.nodes.size(); ++index) {
        for (std::size_t axis = 0U; axis < 3U; ++axis) {
            if (std::abs(model.nodes[index].coordinates[axis]) > 1.0e9) {
                issues.push_back({
                    "bounded_frame3d_coordinate_magnitude_out_of_range",
                    "/nodes/" + std::to_string(index) + "/coordinates_m/"
                        + std::to_string(axis),
                    "Bounded Frame3D coordinates must have magnitude at most 1e9 m.",
                });
            }
        }
    }
    for (std::size_t axis = 0U; axis < 3U; ++axis) {
        if (std::abs(model.coordinate_origin[axis]) > 1.0e9) {
            issues.push_back({
                "bounded_frame3d_coordinate_magnitude_out_of_range",
                "/coordinate_system/origin_m/" + std::to_string(axis),
                "Bounded Frame3D origin coordinates must have magnitude at most 1e9 m.",
            });
        }
    }
    for (std::size_t index = 0U; index < model.materials.size(); ++index) {
        const auto* values = std::get_if<sa_steel_material_parameters_v1>(
            &model.materials[index].parameters);
        if (values == nullptr) {
            continue;
        }
        const auto base = "/materials/" + std::to_string(index) + "/parameters/";
        const auto modulus_valid = [](const double value) {
            return value >= 1.0e-3 && value <= 1.0e18;
        };
        if (!modulus_valid(values->elastic_modulus_pa)) {
            issues.push_back({
                "bounded_frame3d_material_conversion_out_of_range",
                base + "elastic_modulus_pa",
                "Elastic/shear modulus must remain positive and finite after SI conversion.",
            });
        }
        if (values->has_shear_modulus != 0U && !modulus_valid(values->shear_modulus_pa)) {
            issues.push_back({
                "bounded_frame3d_material_conversion_out_of_range",
                base + "shear_modulus_pa",
                "Elastic/shear modulus must remain positive and finite after SI conversion.",
            });
        }
        if (values->yield_stress_pa < 1.0e-6 || values->yield_stress_pa > 1.0e18) {
            issues.push_back({
                "bounded_frame3d_material_conversion_out_of_range",
                base + "yield_stress_pa",
                "Yield stress must remain positive and finite after MPa conversion.",
            });
        }
        const std::array<std::pair<double, const char*>, 3> hardening {{
            {values->isotropic_hardening_modulus_pa, "isotropic_hardening_modulus_pa"},
            {values->kinematic_hardening_modulus_pa, "kinematic_hardening_modulus_pa"},
            {values->yield_tolerance_pa, "yield_tolerance_pa"},
        }};
        for (const auto& [value, name] : hardening) {
            if (value != 0.0 && (value < 1.0e-12 || value > 1.0e18)) {
                issues.push_back({
                    "bounded_frame3d_material_conversion_out_of_range",
                    base + name,
                    "Nonzero hardening/tolerance values must survive MPa conversion.",
                });
            }
        }
    }
    for (std::size_t index = 0U; index < model.sections.size(); ++index) {
        const auto* values = std::get_if<sa_frame_section_parameters_v1>(
            &model.sections[index].parameters);
        if (values == nullptr) {
            continue;
        }
        const auto base = "/sections/" + std::to_string(index) + "/parameters/";
        const std::array<std::pair<double, const char*>, 3> areas {{
            {values->area_m2, "area_m2"},
            {values->shear_area_y_m2, "shear_area_y_m2"},
            {values->shear_area_z_m2, "shear_area_z_m2"},
        }};
        for (const auto& [value, name] : areas) {
            if (value < 1.0e-18 || value > 1.0e12) {
                issues.push_back({
                    "bounded_frame3d_section_value_out_of_range",
                    base + name,
                    "Frame area terms are outside the bounded arithmetic range.",
                });
            }
        }
        const std::array<std::pair<double, const char*>, 3> inertias {{
            {values->iy_m4, "iy_m4"},
            {values->iz_m4, "iz_m4"},
            {values->torsional_constant_m4, "torsional_constant_m4"},
        }};
        for (const auto& [value, name] : inertias) {
            if (value < 1.0e-36 || value > 1.0e36) {
                issues.push_back({
                    "bounded_frame3d_section_value_out_of_range",
                    base + name,
                    "Frame inertia terms are outside the bounded arithmetic range.",
                });
            }
        }
    }
    for (std::size_t index = 0U; index < model.elements.size(); ++index) {
        const auto& rotation = model.elements[index].local_axis_rotation_rad;
        if (rotation.has_value() && std::abs(*rotation) > 1.0e6) {
            issues.push_back({
                "bounded_frame3d_roll_magnitude_out_of_range",
                "/elements/" + std::to_string(index) + "/local_axis_rotation_rad",
                "Local-axis roll is outside the bounded arithmetic range.",
            });
        }
    }
    constexpr std::array<const char*, 6> kLoadNames {"FX", "FY", "FZ", "MX", "MY", "MZ"};
    for (std::size_t pattern = 0U; pattern < model.load_patterns.size(); ++pattern) {
        for (std::size_t load = 0U; load < model.load_patterns[pattern].nodal_loads.size(); ++load) {
            for (std::size_t component = 0U; component < 6U; ++component) {
                if (std::abs(model.load_patterns[pattern].nodal_loads[load].components[component])
                    > 1.0e18) {
                    issues.push_back({
                        "bounded_frame3d_load_magnitude_out_of_range",
                        "/load_patterns/" + std::to_string(pattern) + "/nodal_loads/"
                            + std::to_string(load) + "/components_si/" + kLoadNames[component],
                        "Reference force/moment is outside the bounded arithmetic range.",
                    });
                }
            }
        }
    }
    return issues.size() != initial_size;
}

void add_bounded_frame3d_issues(
    const OwnedModel& model,
    const std::unordered_set<std::string>& node_ids,
    const std::unordered_map<std::string, const Material*>& materials,
    const std::unordered_map<std::string, const Section*>& sections,
    const std::map<std::pair<std::string, std::uint32_t>, double>& constrained_dofs,
    std::vector<Issue>& issues) {
    if (add_bounded_frame3d_numeric_issues(model, issues)) {
        return;
    }
    for (std::size_t index = 0U; index < model.materials.size(); ++index) {
        const auto& material = model.materials[index];
        const auto base = "/materials/" + std::to_string(index);
        if (material.law != SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL) {
            issues.push_back({
                "bounded_frame3d_material_law_unsupported",
                base + "/law_id",
                "Every bounded Frame3D member requires bilinear combined-hardening steel.",
            });
            continue;
        }
        const auto& parameters = std::get<sa_steel_material_parameters_v1>(material.parameters);
        if (parameters.has_shear_modulus == 0U) {
            issues.push_back({
                "bounded_frame3d_shear_modulus_missing",
                base + "/parameters/shear_modulus_pa",
                "Frame3D requires an explicit positive shear modulus; no Poisson fallback is allowed.",
            });
        }
    }

    std::map<std::array<double, 3>, std::string> coordinate_owners;
    bool duplicate_coordinate = false;
    std::map<std::string, std::array<double, 3>> coordinates;
    for (const auto& node : model.nodes) {
        duplicate_coordinate = !coordinate_owners.emplace(node.coordinates, node.identity.id).second
            || duplicate_coordinate;
        coordinates.emplace(node.identity.id, node.coordinates);
    }
    if (duplicate_coordinate) {
        issues.push_back({
            "bounded_frame3d_node_coordinate_duplicate",
            "/nodes",
            "Bounded Frame3D nodes must have unique 3D coordinates.",
        });
    }

    std::map<std::string, std::set<std::string>> graph;
    for (const auto& id : node_ids) {
        graph.emplace(id, std::set<std::string> {});
    }
    std::set<std::pair<std::string, std::string>> member_pairs;
    std::set<std::string> referenced_materials;
    std::set<std::string> referenced_sections;
    for (std::size_t index = 0U; index < model.elements.size(); ++index) {
        const auto& element = model.elements[index];
        const auto base = "/elements/" + std::to_string(index);
        auto pair = std::make_pair(element.node_ids[0], element.node_ids[1]);
        if (pair.second < pair.first) {
            std::swap(pair.first, pair.second);
        }
        if (!member_pairs.insert(pair).second) {
            issues.push_back({
                "bounded_frame3d_parallel_member_unsupported",
                base + "/node_ids",
                "Parallel or duplicate members are outside the bounded v1 profile.",
            });
        }
        if (graph.contains(element.node_ids[0]) && graph.contains(element.node_ids[1])) {
            graph[element.node_ids[0]].insert(element.node_ids[1]);
            graph[element.node_ids[1]].insert(element.node_ids[0]);
        }
        if (element.material_id.has_value()) {
            referenced_materials.insert(*element.material_id);
        }
        referenced_sections.insert(element.section_id);
        const auto nonzero_offset = [](const std::array<double, 3>& offset) {
            return std::any_of(offset.begin(), offset.end(),
                [](const double value) { return value != 0.0; });
        };
        if (nonzero_offset(element.offset_i) || nonzero_offset(element.offset_j)) {
            issues.push_back({
                "bounded_frame3d_rigid_offset_unsupported",
                base + "/offsets",
                "Rigid offsets are not consumed by the bounded Frame3D direct-control solver.",
            });
        }
        if (!element.releases_i.empty() || !element.releases_j.empty()) {
            issues.push_back({
                "bounded_frame3d_release_unsupported",
                base + "/releases",
                "Member end releases are not consumed by the bounded Frame3D direct-control solver.",
            });
        }
    }
    std::set<std::string> material_ids;
    for (const auto& [id, unused] : materials) {
        static_cast<void>(unused);
        material_ids.insert(id);
    }
    if (referenced_materials != material_ids) {
        issues.push_back({
            "bounded_frame3d_material_reference_set_invalid",
            "/materials",
            "Every and only declared bounded Frame3D material must be referenced.",
        });
    }
    std::set<std::string> section_ids;
    for (const auto& [id, unused] : sections) {
        static_cast<void>(unused);
        section_ids.insert(id);
    }
    if (referenced_sections != section_ids) {
        issues.push_back({
            "bounded_frame3d_section_reference_set_invalid",
            "/sections",
            "Every and only declared bounded Frame3D section must be referenced.",
        });
    }
    if (!node_ids.empty()) {
        const auto start = *std::min_element(node_ids.begin(), node_ids.end());
        std::set<std::string> visited {start};
        std::vector<std::string> pending {start};
        while (!pending.empty()) {
            auto current = std::move(pending.back());
            pending.pop_back();
            for (const auto& neighbor : graph[current]) {
                if (visited.insert(neighbor).second) {
                    pending.push_back(neighbor);
                }
            }
        }
        if (visited.size() != node_ids.size()) {
            issues.push_back({
                "bounded_frame3d_graph_disconnected",
                "/elements",
                "The bounded Frame3D member graph must include every node.",
            });
        }
    }

    std::map<std::pair<std::string, std::uint32_t>, double> known_constraints;
    for (const auto& [key, value] : constrained_dofs) {
        if (!node_ids.contains(key.first)) {
            continue;
        }
        known_constraints.emplace(key, value);
        if (value != 0.0) {
            issues.push_back({
                "bounded_frame3d_prescribed_support_unsupported",
                "/constraints",
                "Node " + key.first + " component " + dof_name(key.second)
                    + " must be fixed at zero.",
            });
        }
    }
    const auto equation_count = model.nodes.size() * 6U;
    const auto free_equation_count = equation_count - known_constraints.size();
    if (free_equation_count < 1U || free_equation_count > 768U) {
        issues.push_back({
            "bounded_frame3d_free_equation_count_out_of_range",
            "/constraints",
            "Bounded Frame3D requires between 1 and 768 free equations.",
        });
    }

    if (!coordinates.empty()) {
        std::array<double, 3> minimum {
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
        };
        std::array<double, 3> maximum {
            -std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity(),
        };
        std::array<double, 3> origin {};
        for (const auto& [id, point] : coordinates) {
            static_cast<void>(id);
            for (std::size_t axis = 0U; axis < 3U; ++axis) {
                minimum[axis] = std::min(minimum[axis], point[axis]);
                maximum[axis] = std::max(maximum[axis], point[axis]);
                origin[axis] += point[axis];
            }
        }
        for (auto& value : origin) {
            value /= static_cast<double>(coordinates.size());
        }
        const auto characteristic_length = std::max(
            std::hypot(maximum[0] - minimum[0], maximum[1] - minimum[1],
                maximum[2] - minimum[2]),
            1.0);
        std::vector<std::array<double, 6>> rigid_rows;
        rigid_rows.reserve(known_constraints.size());
        for (const auto& [key, unused] : known_constraints) {
            static_cast<void>(unused);
            const auto& point = coordinates.at(key.first);
            const auto x = (point[0] - origin[0]) / characteristic_length;
            const auto y = (point[1] - origin[1]) / characteristic_length;
            const auto z = (point[2] - origin[2]) / characteristic_length;
            switch (key.second) {
            case SA_DOF_UX:
                rigid_rows.push_back({1.0, 0.0, 0.0, 0.0, z, -y});
                break;
            case SA_DOF_UY:
                rigid_rows.push_back({0.0, 1.0, 0.0, -z, 0.0, x});
                break;
            case SA_DOF_UZ:
                rigid_rows.push_back({0.0, 0.0, 1.0, y, -x, 0.0});
                break;
            case SA_DOF_RX:
                rigid_rows.push_back({0.0, 0.0, 0.0, 1.0, 0.0, 0.0});
                break;
            case SA_DOF_RY:
                rigid_rows.push_back({0.0, 0.0, 0.0, 0.0, 1.0, 0.0});
                break;
            case SA_DOF_RZ:
                rigid_rows.push_back({0.0, 0.0, 0.0, 0.0, 0.0, 1.0});
                break;
            default:
                fail(SA_ERR_INTERNAL, "validated ModelIR DOF became invalid");
            }
        }
        const auto rank = matrix_rank(std::move(rigid_rows));
        if (rank < 6U) {
            issues.push_back({
                "bounded_frame3d_rigid_body_restraint_rank_insufficient",
                "/constraints",
                "Support rows restrain only " + std::to_string(rank) + "/6 rigid-body modes.",
            });
        }
    }

    bool free_reference_load_present = false;
    if (!model.load_patterns.empty()) {
        std::set<std::string> seen_load_nodes;
        const auto& pattern = model.load_patterns.front();
        for (std::size_t index = 0U; index < pattern.nodal_loads.size(); ++index) {
            const auto& load = pattern.nodal_loads[index];
            const auto base = "/load_patterns/0/nodal_loads/" + std::to_string(index);
            if (!seen_load_nodes.insert(load.node_id).second) {
                issues.push_back({
                    "bounded_frame3d_duplicate_nodal_load",
                    base + "/node_id",
                    "Use at most one bounded Frame3D nodal-load row per node.",
                });
            }
            bool row_nonzero = false;
            for (std::size_t component = 0U; component < 6U; ++component) {
                if (load.components[component] == 0.0) {
                    continue;
                }
                row_nonzero = true;
                const auto dof = static_cast<std::uint32_t>(component + 1U);
                if (known_constraints.contains({load.node_id, dof})) {
                    constexpr std::array<const char*, 6> kNames {
                        "FX", "FY", "FZ", "MX", "MY", "MZ"};
                    issues.push_back({
                        "bounded_frame3d_reference_load_on_restrained_dof",
                        base + "/components_si/" + kNames[component],
                        "Reference loads on restrained equations are outside the bounded profile.",
                    });
                } else {
                    free_reference_load_present = true;
                }
            }
            if (!row_nonzero) {
                issues.push_back({
                    "bounded_frame3d_zero_nodal_load",
                    base + "/components_si",
                    "A declared bounded Frame3D reference-load row must be nonzero.",
                });
            }
        }
    }
    if (!free_reference_load_present) {
        issues.push_back({
            "bounded_frame3d_free_reference_load_missing",
            "/load_patterns/0/nodal_loads",
            "Direct displacement control requires a nonzero reference load on a free equation.",
        });
    }
}



[[nodiscard]] std::vector<Issue> semantic_issues(const OwnedModel& model) {
    auto issues = finite_issues(model);
    if (!issues.empty()) {
        return issues;
    }
    add_unit_scale_issues(model, issues);

    const auto identity = [](const auto& row) -> const Entity& { return row.identity; };
    add_indexed_family_issues(model.nodes, "nodes", identity, issues);
    add_indexed_family_issues(model.materials, "materials", identity, issues);
    add_indexed_family_issues(model.sections, "sections", identity, issues);
    add_indexed_family_issues(model.elements, "elements", identity, issues);
    add_indexed_family_issues(model.constraints, "constraints", identity, issues);
    add_indexed_family_issues(model.load_patterns, "load_patterns", identity, issues);
    add_indexed_family_issues(
        model.load_combinations, "load_combinations", identity, issues);
    add_plain_indexed_family_issues(
        model.time_functions,
        "time_functions",
        [](const auto& row) { return row.id; },
        [](const auto& row) { return row.index; },
        issues);
    add_plain_indexed_family_issues(
        model.construction_stages,
        "construction_stages",
        [](const auto& row) { return row.id; },
        [](const auto& row) { return row.index; },
        issues);

    const auto node_ids = entity_ids(model.nodes);
    const auto material_ids = entity_ids(model.materials);
    const auto element_ids = entity_ids(model.elements);
    const auto constraint_ids = entity_ids(model.constraints);
    const auto load_pattern_ids = entity_ids(model.load_patterns);
    const auto load_combination_ids = entity_ids(model.load_combinations);
    std::unordered_set<std::string> time_function_ids;
    std::unordered_set<std::string> construction_stage_ids;
    for (const auto& row : model.time_functions) {
        time_function_ids.insert(row.id);
    }
    for (const auto& row : model.construction_stages) {
        construction_stage_ids.insert(row.id);
    }
    std::unordered_map<std::string, std::array<double, 3>> coordinates;
    for (const auto& node : model.nodes) {
        coordinates.emplace(node.identity.id, node.coordinates);
    }
    std::unordered_map<std::string, const Section*> sections;
    for (const auto& section : model.sections) {
        sections.emplace(section.identity.id, &section);
    }
    std::unordered_map<std::string, const Material*> materials;
    for (const auto& material : model.materials) {
        materials.emplace(material.identity.id, &material);
    }
    const bool bounded_planar =
        model.capability_profile == SA_MODEL_IR_PROFILE_BOUNDED_PLANAR_FRAME_ALPHA
        || model.capability_profile == SA_MODEL_IR_PROFILE_PLANAR_FRAME_VERIFIED_ALPHA_V1;

    for (std::size_t index = 0U; index < model.elements.size(); ++index) {
        const auto& element = model.elements[index];
        const auto base = "/elements/" + std::to_string(index);
        if (element.node_ids[0] == element.node_ids[1]) {
            issues.push_back({
                "element_nodes_not_distinct",
                base + "/node_ids",
                "Element end nodes must differ.",
            });
        }
        for (const auto& node_id : element.node_ids) {
            if (!node_ids.contains(node_id)) {
                add_missing_reference(issues, base + "/node_ids", "node", node_id);
            }
        }
        const auto section = sections.find(element.section_id);
        if (section == sections.end()) {
            add_missing_reference(issues, base + "/section_id", "section", element.section_id);
        } else {
            const auto expected = bounded_planar
                ? SA_SECTION_RECTANGULAR_RC_FIBER_2D
                : (element.type == SA_ELEMENT_FRAME_3D ? SA_SECTION_FRAME_3D
                                                       : SA_SECTION_TRUSS_3D);
            if (section->second->family != expected) {
                issues.push_back({
                    "element_section_family_mismatch",
                    base + "/section_id",
                    "Element type and section family do not agree.",
                });
            }
        }
        if (!bounded_planar && element.material_id.has_value()
            && !material_ids.contains(*element.material_id)) {
            add_missing_reference(
                issues, base + "/material_id", "material", *element.material_id);
        }
        const auto start_node = coordinates.find(element.node_ids[0]);
        const auto end_node = coordinates.find(element.node_ids[1]);
        if (start_node != coordinates.end() && end_node != coordinates.end()) {
            std::array<double, 3> delta {};
            for (std::size_t axis = 0U; axis < 3U; ++axis) {
                const auto start = start_node->second[axis] + element.offset_i[axis];
                const auto end = end_node->second[axis] + element.offset_j[axis];
                delta[axis] = end - start;
            }
            const auto length = std::hypot(delta[0], delta[1], delta[2]);
            if (!std::isfinite(length)) {
                issues.push_back({
                    "element_effective_length_not_finite",
                    base,
                    "Element length after offsets must remain finite.",
                });
            }
            if (length <= kZeroLengthToleranceM) {
                issues.push_back({
                    "element_zero_effective_length",
                    base,
                    "Element length after offsets must exceed 1e-12 m.",
                });
            }
        }
    }

    std::map<std::pair<std::string, std::uint32_t>, double> constrained_dofs;
    for (std::size_t index = 0U; index < model.constraints.size(); ++index) {
        const auto& constraint = model.constraints[index];
        const auto base = "/constraints/" + std::to_string(index);
        if (!node_ids.contains(constraint.node_id)) {
            add_missing_reference(issues, base + "/node_id", "node", constraint.node_id);
        }
        std::map<std::uint32_t, double> prescribed;
        for (const auto& value : constraint.prescribed_values) {
            prescribed.emplace(value.dof, value.value);
            if (std::find(constraint.dofs.begin(), constraint.dofs.end(), value.dof)
                == constraint.dofs.end()) {
                issues.push_back({
                    "prescribed_value_dof_not_restrained",
                    base + "/prescribed_values_si",
                    "Prescribed-value DOFs must also appear in the restrained DOF list.",
                });
                break;
            }
        }
        for (const auto dof : constraint.dofs) {
            const auto found = prescribed.find(dof);
            const auto value = found == prescribed.end() ? 0.0 : found->second;
            const auto key = std::make_pair(constraint.node_id, dof);
            const auto existing = constrained_dofs.find(key);
            if (existing != constrained_dofs.end()) {
                const auto conflict = existing->second != value;
                issues.push_back({
                    "duplicate_constrained_dof",
                    base + "/dofs",
                    "Node " + constraint.node_id + " DOF " + dof_name(dof) + ": "
                        + (conflict ? "Conflicting prescribed values."
                                    : "DOF is restrained more than once."),
                });
            } else {
                constrained_dofs.emplace(key, value);
            }
        }
    }

    std::unordered_set<std::string> nested_load_ids;
    bool nested_duplicate_id = false;
    for (std::size_t pattern_index = 0U; pattern_index < model.load_patterns.size();
         ++pattern_index) {
        const auto& pattern = model.load_patterns[pattern_index];
        const auto base = "/load_patterns/" + std::to_string(pattern_index);
        add_indexed_family_issues(
            pattern.nodal_loads,
            "load_patterns/" + std::to_string(pattern_index) + "/nodal_loads",
            identity,
            issues);
        bool nonzero = std::any_of(pattern.self_weight.begin(), pattern.self_weight.end(),
            [](const double value) { return value != 0.0; });
        for (std::size_t load_index = 0U; load_index < pattern.nodal_loads.size(); ++load_index) {
            const auto& load = pattern.nodal_loads[load_index];
            nested_duplicate_id = !nested_load_ids.insert(load.identity.id).second
                || nested_duplicate_id;
            if (!node_ids.contains(load.node_id)) {
                add_missing_reference(
                    issues,
                    base + "/nodal_loads/" + std::to_string(load_index) + "/node_id",
                    "node",
                    load.node_id);
            }
            nonzero = nonzero
                || std::any_of(load.components.begin(), load.components.end(),
                    [](const double value) { return value != 0.0; });
        }
        if (!nonzero && !bounded_planar) {
            issues.push_back({
                "load_pattern_all_zero",
                base,
                "Each load pattern must contain a non-zero load.",
            });
        }
    }
    if (nested_duplicate_id) {
        issues.push_back({
            "duplicate_id",
            "/load_patterns/*/nodal_loads",
            "Nodal-load IDs must be unique across all load patterns.",
        });
    }

    add_load_combination_issues(
        model, load_pattern_ids, load_combination_ids, issues);

    for (std::size_t index = 0U; index < model.construction_stages.size(); ++index) {
        const auto& stage = model.construction_stages[index];
        const auto base = "/construction_stages/" + std::to_string(index);
        for (const auto& id : stage.active_element_ids) {
            if (!element_ids.contains(id)) {
                add_missing_reference(issues, base + "/active_element_ids", "element", id);
            }
        }
        for (const auto& id : stage.active_constraint_ids) {
            if (!constraint_ids.contains(id)) {
                add_missing_reference(
                    issues, base + "/active_constraint_ids", "constraint", id);
            }
        }
        for (const auto& id : stage.load_pattern_ids) {
            if (!load_pattern_ids.contains(id)) {
                add_missing_reference(issues, base + "/load_pattern_ids", "load_pattern", id);
            }
        }
    }
    for (std::size_t index = 0U; index < model.time_functions.size(); ++index) {
        const auto& points = model.time_functions[index].points;
        for (std::size_t point = 1U; point < points.size(); ++point) {
            if (points[point].time <= points[point - 1U].time) {
                issues.push_back({
                    "time_function_not_strictly_increasing",
                    "/time_functions/" + std::to_string(index) + "/points",
                    "Time-function coordinates must be strictly increasing.",
                });
                break;
            }
        }
    }

    const std::array<std::pair<std::uint32_t, const std::unordered_set<std::string>*>, 9>
        ids_by_kind {{
            {SA_MODEL_IR_ENTITY_NODE, &node_ids},
            {SA_MODEL_IR_ENTITY_MATERIAL, &material_ids},
            {SA_MODEL_IR_ENTITY_SECTION, nullptr},
            {SA_MODEL_IR_ENTITY_ELEMENT, &element_ids},
            {SA_MODEL_IR_ENTITY_CONSTRAINT, &constraint_ids},
            {SA_MODEL_IR_ENTITY_LOAD_PATTERN, &load_pattern_ids},
            {SA_MODEL_IR_ENTITY_LOAD_COMBINATION, &load_combination_ids},
            {SA_MODEL_IR_ENTITY_TIME_FUNCTION, &time_function_ids},
            {SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE, &construction_stage_ids},
        }};
    const auto section_ids = entity_ids(model.sections);
    std::unordered_set<std::string> all_entity_ids;
    const std::array<const std::unordered_set<std::string>*, 9> all_id_sets {
        &node_ids,
        &material_ids,
        &section_ids,
        &element_ids,
        &constraint_ids,
        &load_pattern_ids,
        &load_combination_ids,
        &time_function_ids,
        &construction_stage_ids,
    };
    for (const auto* ids : all_id_sets) {
        all_entity_ids.insert(ids->begin(), ids->end());
    }
    for (std::size_t index = 0U; index < model.roundtrip_rows.size(); ++index) {
        const auto& row = model.roundtrip_rows[index];
        const auto base = "/roundtrip_map/" + std::to_string(index);
        if (!all_entity_ids.contains(row.model_ir_entity_id)) {
            add_missing_reference(
                issues,
                base + "/model_ir_entity_id",
                "model_ir_entity",
                row.model_ir_entity_id);
            continue;
        }
        const std::unordered_set<std::string>* expected = nullptr;
        for (const auto& [kind, ids] : ids_by_kind) {
            if (kind == row.entity_kind) {
                expected = kind == SA_MODEL_IR_ENTITY_SECTION ? &section_ids : ids;
                break;
            }
        }
        if (expected == nullptr || !expected->contains(row.model_ir_entity_id)) {
            issues.push_back({
                "roundtrip_entity_kind_mismatch",
                base + "/entity_kind",
                "Roundtrip entity kind does not match the referenced ModelIR entity.",
            });
        }
    }
    if (bounded_planar) {
        add_bounded_planar_issues(
            model, node_ids, materials, sections, constrained_dofs, issues);
    }
    if (model.capability_profile
        == SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL) {
        add_bounded_frame3d_issues(
            model, node_ids, materials, sections, constrained_dofs, issues);
    }
    return issues;
}

[[nodiscard]] const char* entity_kind_name(const std::uint32_t kind) {
    switch (kind) {
    case SA_MODEL_IR_ENTITY_NODE:
        return "node";
    case SA_MODEL_IR_ENTITY_MATERIAL:
        return "material";
    case SA_MODEL_IR_ENTITY_SECTION:
        return "section";
    case SA_MODEL_IR_ENTITY_ELEMENT:
        return "element";
    case SA_MODEL_IR_ENTITY_CONSTRAINT:
        return "constraint";
    case SA_MODEL_IR_ENTITY_LOAD_PATTERN:
        return "load_pattern";
    case SA_MODEL_IR_ENTITY_LOAD_COMBINATION:
        return "load_combination";
    case SA_MODEL_IR_ENTITY_TIME_FUNCTION:
        return "time_function";
    case SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE:
        return "construction_stage";
    default:
        fail(SA_ERR_INTERNAL, "validated ModelIR entity kind became invalid");
    }
}

[[nodiscard]] std::string json_string(const std::string_view value) {
    constexpr char kHex[] = "0123456789abcdef";
    std::string output;
    output.reserve(value.size() + 2U);
    output.push_back('"');
    for (const char raw : value) {
        const auto byte = static_cast<unsigned char>(raw);
        switch (byte) {
        case '"':
            output += "\\\"";
            break;
        case '\\':
            output += "\\\\";
            break;
        case '\b':
            output += "\\b";
            break;
        case '\f':
            output += "\\f";
            break;
        case '\n':
            output += "\\n";
            break;
        case '\r':
            output += "\\r";
            break;
        case '\t':
            output += "\\t";
            break;
        default:
            if (byte < 0x20U) {
                output += "\\u00";
                output.push_back(kHex[static_cast<std::size_t>(byte >> 4U)]);
                output.push_back(kHex[static_cast<std::size_t>(byte & 0x0fU)]);
            } else {
                output.push_back(raw);
            }
        }
    }
    output.push_back('"');
    return output;
}

[[nodiscard]] std::vector<std::string> derived_blockers(const OwnedModel& model) {
    std::set<std::string> unique;
    for (const auto& row : model.roundtrip_rows) {
        if (row.mapping_status != SA_ROUNDTRIP_UNSUPPORTED) {
            continue;
        }
        const auto identity = std::string {"{\"entity_kind\":"}
            + json_string(entity_kind_name(row.entity_kind))
            + ",\"mapping_status\":\"unsupported\",\"model_ir_entity_id\":"
            + json_string(row.model_ir_entity_id) + ",\"source_entity_id\":"
            + json_string(row.source_entity_id) + "}";
        unique.insert("derived.roundtrip.unsupported." + sha256_hex(identity).substr(0U, 16U));
    }
    return {unique.begin(), unique.end()};
}

[[nodiscard]] std::vector<std::string> declared_blockers(const OwnedModel& model) {
    std::set<std::string> unique;
    for (const auto& feature : model.unsupported_features) {
        if (feature.blocking) {
            unique.insert(feature.feature_id);
        }
    }
    return {unique.begin(), unique.end()};
}

void append_string_array(std::string& output, const std::vector<std::string>& values) {
    output.push_back('[');
    for (std::size_t index = 0U; index < values.size(); ++index) {
        if (index != 0U) {
            output.push_back(',');
        }
        output += json_string(values[index]);
    }
    output.push_back(']');
}

[[nodiscard]] std::string make_report(
    const OwnedModel& model,
    const std::vector<Issue>& issues,
    const std::vector<std::string>& declared,
    const std::vector<std::string>& derived) {
    std::set<std::string> blocker_set(declared.begin(), declared.end());
    blocker_set.insert(derived.begin(), derived.end());
    const std::vector<std::string> blockers(blocker_set.begin(), blocker_set.end());
    const bool semantics_valid = issues.empty();
    const bool analysis_ready = semantics_valid && blockers.empty();
    std::string output;
    output.reserve(1024U + issues.size() * 192U);
    output += "{\"schema_version\":\"structural-model-ir-cpp-validation.v1\"";
    output += ",\"model_ir_schema_version\":" + json_string(model.schema_version);
    output += ",\"model_id\":" + json_string(model.model_id);
    output += ",\"schema_valid\":true";
    output += semantics_valid ? ",\"semantics_valid\":true" : ",\"semantics_valid\":false";
    output += semantics_valid ? ",\"contract_valid\":true" : ",\"contract_valid\":false";
    output += analysis_ready ? ",\"analysis_ready\":true" : ",\"analysis_ready\":false";
    output += ",\"issues\":[";
    for (std::size_t index = 0U; index < issues.size(); ++index) {
        if (index != 0U) {
            output.push_back(',');
        }
        output += "{\"code\":" + json_string(issues[index].code) + ",\"path\":"
            + json_string(issues[index].path) + ",\"detail\":"
            + json_string(issues[index].detail) + "}";
    }
    output += "],\"blocking_feature_ids\":";
    append_string_array(output, blockers);
    output += ",\"declared_blocking_feature_ids\":";
    append_string_array(output, declared);
    output += ",\"derived_blocking_feature_ids\":";
    append_string_array(output, derived);
    output += ",\"content_hash\":" + json_string(model.content_hash);
    output += ",\"semantic_hash\":" + json_string(model.semantic_hash);
    output += ",\"provenance_hash\":" + json_string(model.provenance_hash);
    output += ",\"entity_counts\":{";
    output += "\"nodes\":" + std::to_string(model.nodes.size());
    output += ",\"materials\":" + std::to_string(model.materials.size());
    output += ",\"sections\":" + std::to_string(model.sections.size());
    output += ",\"elements\":" + std::to_string(model.elements.size());
    output += ",\"constraints\":" + std::to_string(model.constraints.size());
    output += ",\"load_patterns\":" + std::to_string(model.load_patterns.size());
    output += ",\"load_combinations\":" + std::to_string(model.load_combinations.size());
    output += ",\"time_functions\":" + std::to_string(model.time_functions.size());
    output += ",\"construction_stages\":" + std::to_string(model.construction_stages.size());
    output += ",\"roundtrip_map\":" + std::to_string(model.roundtrip_rows.size());
    output += ",\"unsupported_features\":"
        + std::to_string(model.unsupported_features.size()) + "}";
    output += ",\"abi_version\":" + std::to_string(SA_ABI_V1_1);
    output += ",\"library_build_identity\":\"structural-native-0.1.0+cxx20\"";
    output += ",\"claim_boundary\":"
        "\"model_ir_contract_validation_not_solver_or_backend_readiness\"}";
    return output;
}

} // namespace

struct Model::Impl {
    explicit Impl(OwnedModel source)
        : model(std::move(source)) {
        issues = semantic_issues(model);
        std::sort(issues.begin(), issues.end(), [](const auto& left, const auto& right) {
            return left.ordering_key() < right.ordering_key();
        });
        issues.erase(std::unique(issues.begin(), issues.end(), [](const auto& left, const auto& right) {
                         return left.ordering_key() == right.ordering_key();
                     }),
            issues.end());
        declared = declared_blockers(model);
        derived = derived_blockers(model);
        report = make_report(model, issues, declared, derived);
    }

    OwnedModel model;
    std::vector<Issue> issues;
    std::vector<std::string> declared;
    std::vector<std::string> derived;
    std::string report;
};

Error::Error(const sa_status_code_v1 status, const char* const message)
    : std::runtime_error(message)
    , status_(status) {}

sa_status_code_v1 Error::status() const noexcept {
    return status_;
}

Model::Model(const sa_model_ir_descriptor_v1& descriptor)
    : impl_(std::make_unique<Impl>(copy_model(descriptor))) {}

Model::~Model() = default;

std::string_view Model::validation_report() const noexcept {
    return impl_->report;
}

std::string_view Model::snapshot() const noexcept {
    return impl_->model.canonical_json;
}

NdthaAdapterProperties Model::adapt_fixed_guided_frame3d_x(
    const std::string_view element_id,
    const std::string_view base_node_id,
    const std::string_view floor_node_id,
    const std::string_view load_pattern_id,
    const double damping_ratio) const {
    if (!impl_->issues.empty()) {
        fail(SA_ERR_SEMANTIC_INVALID, "ModelIR NDTHA adapter requires a semantically valid model");
    }
    if (!impl_->declared.empty() || !impl_->derived.empty()) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR NDTHA adapter requires an analysis-ready model");
    }
    if (!std::isfinite(damping_ratio) || damping_ratio < 0.0 || damping_ratio > 1.0) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR NDTHA adapter damping ratio is outside [0, 1]");
    }

    const auto& model = impl_->model;
    const bool exact_family_shape =
        model.capability_profile == SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D
        && model.nodes.size() == 2U && model.materials.size() == 1U
        && model.sections.size() == 1U && model.elements.size() == 1U
        && model.constraints.size() == 2U && model.load_patterns.size() == 1U
        && model.load_combinations.empty() && model.time_functions.empty()
        && model.construction_stages.empty() && model.roundtrip_rows.empty()
        && model.unsupported_features.empty();
    if (!exact_family_shape) {
        fail(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR does not match the fixed-guided one-story frame3d adapter profile");
    }

    const auto find_node = [&model](const std::string_view id) -> const Node* {
        const auto found = std::find_if(model.nodes.begin(), model.nodes.end(), [id](const auto& row) {
            return row.identity.id == id;
        });
        return found == model.nodes.end() ? nullptr : &*found;
    };
    const auto* const base = find_node(base_node_id);
    const auto* const floor = find_node(floor_node_id);
    const auto& element = model.elements.front();
    const auto& material = model.materials.front();
    const auto& section = model.sections.front();
    const auto& pattern = model.load_patterns.front();
    if (base == nullptr || floor == nullptr || base == floor
        || element.identity.id != element_id || pattern.identity.id != load_pattern_id) {
        fail(SA_ERR_INVALID_ARGUMENT, "ModelIR NDTHA adapter selector does not identify the bounded profile");
    }
    const auto all_zero = [](const auto& values) {
        return std::all_of(values.begin(), values.end(), [](const double value) {
            return value == 0.0;
        });
    };
    const bool element_supported = element.type == SA_ELEMENT_FRAME_3D
        && element.formulation == SA_FORMULATION_EULER_BERNOULLI_3D
        && element.node_ids[0] == base_node_id && element.node_ids[1] == floor_node_id
        && element.material_id.has_value() && *element.material_id == material.identity.id
        && element.section_id == section.identity.id
        && element.local_axis_rotation_rad.has_value()
        && *element.local_axis_rotation_rad == 0.0 && all_zero(element.offset_i)
        && all_zero(element.offset_j) && element.releases_i.empty()
        && element.releases_j.empty() && !element.integration_order.has_value()
        && !element.uniform_load.has_value();
    if (!element_supported || material.law != SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC
        || section.family != SA_SECTION_FRAME_3D) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR element, material, or section is outside the adapter profile");
    }

    const bool vertical_global_z = base->coordinates[0] == floor->coordinates[0]
        && base->coordinates[1] == floor->coordinates[1]
        && floor->coordinates[2] > base->coordinates[2];
    if (!vertical_global_z) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR adapter element must be vertical in global Z");
    }

    const auto find_constraint = [&model](const std::string_view node_id) -> const Constraint* {
        const auto found = std::find_if(
            model.constraints.begin(), model.constraints.end(), [node_id](const auto& row) {
                return row.node_id == node_id;
            });
        return found == model.constraints.end() ? nullptr : &*found;
    };
    const auto* const base_constraint = find_constraint(base_node_id);
    const auto* const floor_constraint = find_constraint(floor_node_id);
    const std::vector<std::uint32_t> fixed_dofs {
        SA_DOF_UX, SA_DOF_UY, SA_DOF_UZ, SA_DOF_RX, SA_DOF_RY, SA_DOF_RZ};
    const std::vector<std::uint32_t> guided_dofs {
        SA_DOF_UY, SA_DOF_UZ, SA_DOF_RX, SA_DOF_RY, SA_DOF_RZ};
    if (base_constraint == nullptr || floor_constraint == nullptr
        || base_constraint == floor_constraint
        || base_constraint->dofs != fixed_dofs || floor_constraint->dofs != guided_dofs
        || !base_constraint->prescribed_values.empty()
        || !floor_constraint->prescribed_values.empty()) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR constraints do not match fixed-guided global-X motion");
    }

    if (pattern.analysis_type != SA_ANALYSIS_LINEAR_STATIC || !all_zero(pattern.self_weight)
        || pattern.nodal_loads.size() != 1U
        || pattern.nodal_loads.front().node_id != floor_node_id) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR load pattern does not match one floor FX load");
    }
    const auto& load = pattern.nodal_loads.front();
    if (load.components[0] == 0.0
        || !std::all_of(load.components.begin(), load.components.end(), [](const double value) {
               return std::isfinite(value);
           })
        || !std::all_of(load.components.begin() + 1, load.components.end(), [](const double value) {
               return value == 0.0;
           })) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR adapter floor load must be a finite nonzero FX load");
    }

    const auto& linear = std::get<sa_linear_material_parameters_v1>(material.parameters);
    const auto& frame = std::get<sa_frame_section_parameters_v1>(section.parameters);
    const double height = floor->coordinates[2] - base->coordinates[2];
    const double stiffness = 12.0 * linear.elastic_modulus_pa * frame.iy_m4
        / (height * height * height);
    const double mass = 0.5 * linear.density_kg_m3 * frame.area_m2 * height;
    const double damping = 2.0 * damping_ratio * std::sqrt(stiffness * mass);
    const std::array derived {
        height,
        linear.elastic_modulus_pa,
        frame.area_m2,
        frame.iy_m4,
        stiffness,
        mass,
        damping,
        load.components[0],
    };
    if (!std::all_of(derived.begin(), derived.end(), [](const double value) {
            return std::isfinite(value);
        })
        || height <= 0.0 || linear.elastic_modulus_pa <= 0.0 || frame.area_m2 <= 0.0
        || frame.iy_m4 <= 0.0 || stiffness <= 0.0 || mass <= 0.0 || damping < 0.0) {
        fail(SA_ERR_ANALYSIS_NOT_READY, "ModelIR adapter derived property is outside its physical domain");
    }

    return {
        element.identity.index,
        pattern.identity.index,
        height,
        linear.elastic_modulus_pa,
        frame.area_m2,
        frame.iy_m4,
        stiffness,
        mass,
        damping,
        load.components[0],
    };
}

} // namespace structural::model_ir
