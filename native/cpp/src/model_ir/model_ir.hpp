#ifndef STRUCTURAL_MODEL_IR_INTERNAL_HPP
#define STRUCTURAL_MODEL_IR_INTERNAL_HPP

#include "structural/abi_v1.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace structural::model_ir {

struct NdthaAdapterProperties final {
    std::uint64_t element_index {};
    std::uint64_t load_pattern_index {};
    double story_height_m {};
    double youngs_modulus_pa {};
    double section_area_m2 {};
    double section_iy_m4 {};
    double story_stiffness_n_per_m {};
    double story_mass_kg {};
    double story_damping_n_s_per_m {};
    double floor_load_base_n {};
};

/// One typed, resolved element admitted by the bounded linear reference-assembly projection.
struct LinearReferenceElement final {
    std::uint64_t stable_index {};
    std::uint32_t type {};
    std::uint32_t node_i_index {};
    std::uint32_t node_j_index {};
    std::array<double, 3> node_i_m {};
    std::array<double, 3> node_j_m {};
    double youngs_modulus_pa {};
    double poisson_ratio {};
    double density_kg_per_m3 {};
    double area_m2 {};
    double iy_m4 {};
    double iz_m4 {};
    double torsional_constant_m4 {};
    double local_axis_rotation_rad {};
    std::array<double, 3> offset_i_global_m {};
    std::array<double, 3> offset_j_global_m {};
    std::vector<std::uint32_t> releases_i {};
    std::vector<std::uint32_t> releases_j {};
};

struct LinearReferenceNodalLoad final {
    std::uint32_t node_index {};
    std::array<double, 6> components_si {};
};

struct LinearReferenceLoadPattern final {
    std::string id;
    std::uint64_t stable_index {};
    std::uint32_t analysis_type {};
    std::array<double, 3> self_weight {};
    std::vector<LinearReferenceNodalLoad> nodal_loads;
};

struct LinearReferenceLoadCombinationTerm final {
    std::string ref_id;
    std::uint32_t ref_kind {};
    double factor {};
};

struct LinearReferenceLoadCombination final {
    std::string id;
    std::uint64_t stable_index {};
    std::vector<LinearReferenceLoadCombinationTerm> terms;
};

/// Deep, pointer-free projection from validated ModelIR into the bounded linear C1 graph slice.
struct LinearReferenceGraph final {
    std::string content_hash;
    std::string semantic_hash;
    std::string provenance_hash;
    std::size_t global_dof_count {};
    std::vector<LinearReferenceElement> elements;
    std::vector<std::uint32_t> constrained_dof_indices;
    std::vector<LinearReferenceLoadPattern> load_patterns;
    std::vector<LinearReferenceLoadCombination> load_combinations;
};

class Error final : public std::runtime_error {
public:
    Error(sa_status_code_v1 status, const char* message);

    [[nodiscard]] sa_status_code_v1 status() const noexcept;

private:
    sa_status_code_v1 status_;
};

class Model final {
public:
    explicit Model(const sa_model_ir_descriptor_v1& descriptor);
    ~Model();

    Model(const Model&) = delete;
    Model& operator=(const Model&) = delete;
    Model(Model&&) = delete;
    Model& operator=(Model&&) = delete;

    [[nodiscard]] std::string_view validation_report() const noexcept;
    [[nodiscard]] std::string_view snapshot() const noexcept;
    [[nodiscard]] LinearReferenceGraph project_linear_reference_graph() const;
    [[nodiscard]] NdthaAdapterProperties adapt_fixed_guided_frame3d_x(
        std::string_view element_id,
        std::string_view base_node_id,
        std::string_view floor_node_id,
        std::string_view load_pattern_id,
        double damping_ratio) const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace structural::model_ir

#endif
