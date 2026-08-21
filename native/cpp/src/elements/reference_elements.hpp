#ifndef STRUCTURAL_ELEMENTS_REFERENCE_ELEMENTS_HPP
#define STRUCTURAL_ELEMENTS_REFERENCE_ELEMENTS_HPP

#include "../materials/materials.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace structural::elements {

enum class ReferenceElementKind {
    truss3d = 1,
    frame3d = 2,
    shell3_membrane = 3,
};

struct ElementOperatorResponse {
    ReferenceElementKind kind;
    std::size_t dof_count;
    std::vector<double> tangent;
    std::vector<double> consistent_mass;
    std::vector<double> residual;
    std::vector<double> jvp;
    std::vector<double> recovery;
};

struct Truss3dInput {
    std::array<double, 3> node_i_m;
    std::array<double, 3> node_j_m;
    materials::ElasticIsotropic material;
    double area_m2;
    std::span<const double> displacement_m;
    std::span<const double> direction_m;
};

struct Frame3dInput {
    std::array<double, 3> node_i_m;
    std::array<double, 3> node_j_m;
    materials::ElasticIsotropic material;
    double area_m2;
    double iy_m4;
    double iz_m4;
    double torsional_constant_m4;
    double local_axis_rotation_rad;
    std::span<const double> displacement;
    std::span<const double> direction;
    std::array<double, 3> offset_i_global_m {};
    std::array<double, 3> offset_j_global_m {};
    // Zero-based local UX..RZ components released at each element end.
    std::span<const std::uint32_t> releases_i {};
    std::span<const std::uint32_t> releases_j {};
};

struct Frame3dUniformDistributedLoadInput {
    std::array<double, 3> node_i_m;
    std::array<double, 3> node_j_m;
    materials::ElasticIsotropic material;
    double area_m2;
    double iy_m4;
    double iz_m4;
    double torsional_constant_m4;
    double local_axis_rotation_rad;
    std::array<double, 3> components_local_n_per_m;
    std::array<double, 3> offset_i_global_m {};
    std::array<double, 3> offset_j_global_m {};
    std::span<const std::uint32_t> releases_i {};
    std::span<const std::uint32_t> releases_j {};
};

struct Frame3dUniformDistributedLoadResponse {
    std::array<double, 12> global_equivalent_load;
    std::array<double, 12> local_recovery_equivalent;
};

struct Frame3dGeometricStiffnessInput {
    std::array<double, 3> node_i_m;
    std::array<double, 3> node_j_m;
    materials::ElasticIsotropic material;
    double area_m2;
    double iy_m4;
    double iz_m4;
    double torsional_constant_m4;
    double local_axis_rotation_rad;
    // Positive compression magnitude in the initial-stress state.
    double axial_compression_n;
    std::array<double, 3> offset_i_global_m {};
    std::array<double, 3> offset_j_global_m {};
    std::span<const std::uint32_t> releases_i {};
    std::span<const std::uint32_t> releases_j {};
};

struct Shell3MembraneInput {
    std::array<std::array<double, 3>, 3> nodes_m;
    materials::ElasticIsotropic material;
    double thickness_m;
    std::span<const double> displacement_m;
    std::span<const double> direction_m;
};

[[nodiscard]] ElementOperatorResponse evaluate_truss3d(const Truss3dInput& input);
[[nodiscard]] ElementOperatorResponse evaluate_frame3d(const Frame3dInput& input);
[[nodiscard]] Frame3dUniformDistributedLoadResponse
evaluate_frame3d_uniform_distributed_load(
    const Frame3dUniformDistributedLoadInput& input);
/// Return the positive-semidefinite beam-column geometric operator used by
/// `K phi = lambda Kg phi` for one constant compressive axial-force state.
[[nodiscard]] std::vector<double> evaluate_frame3d_geometric_stiffness(
    const Frame3dGeometricStiffnessInput& input);
[[nodiscard]] ElementOperatorResponse evaluate_shell3_membrane(
    const Shell3MembraneInput& input);

}  // namespace structural::elements

#endif
