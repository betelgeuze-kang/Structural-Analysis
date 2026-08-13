#include "model_ir_assembly.hpp"

#include "../elements/reference_elements.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

namespace structural::assembly {
namespace {

struct OwnedContribution final {
    std::uint64_t stable_index {};
    std::uint32_t element_type {};
    std::vector<std::uint32_t> dof_indices;
    elements::ElementOperatorResponse response;
};

[[nodiscard]] bool all_finite(const std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](const double value) {
        return std::isfinite(value);
    });
}

[[nodiscard]] std::uint32_t global_dof(
    const std::uint32_t node_index,
    const std::uint32_t component) {
    return node_index * 6U + component;
}

template <std::size_t Size>
[[nodiscard]] std::array<double, Size> gather(
    const std::span<const double> source,
    const std::span<const std::uint32_t> indices) {
    if (indices.size() != Size) {
        throw model_ir::Error(SA_ERR_INTERNAL, "projected element DOF count became invalid");
    }
    std::array<double, Size> output {};
    for (std::size_t index = 0U; index < Size; ++index) {
        output[index] = source[indices[index]];
    }
    return output;
}

[[nodiscard]] std::vector<std::uint32_t> frame_dofs(
    const model_ir::LinearReferenceElement& element) {
    std::vector<std::uint32_t> output;
    output.reserve(12U);
    for (const auto node : {element.node_i_index, element.node_j_index}) {
        for (auto component = std::uint32_t {0U}; component < 6U; ++component) {
            output.push_back(global_dof(node, component));
        }
    }
    return output;
}

[[nodiscard]] std::vector<std::uint32_t> truss_dofs(
    const model_ir::LinearReferenceElement& element) {
    std::vector<std::uint32_t> output;
    output.reserve(6U);
    for (const auto node : {element.node_i_index, element.node_j_index}) {
        for (auto component = std::uint32_t {0U}; component < 3U; ++component) {
            output.push_back(global_dof(node, component));
        }
    }
    return output;
}

}  // namespace

ModelIrLinearAssemblySizes model_ir_linear_reference_sizes(const model_ir::Model& model) {
    const auto graph = model.project_linear_reference_graph();
    if (graph.global_dof_count > SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT
        || graph.elements.size() > SA_MODEL_IR_LINEAR_MAX_RECOVERY_RECORD_COUNT) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR linear reference graph exceeds the public ABI size bounds");
    }
    std::vector<bool> constrained(graph.global_dof_count, false);
    for (const auto dof : graph.constrained_dof_indices) {
        constrained[dof] = true;
    }
    const auto active_dof_count = graph.global_dof_count - graph.constrained_dof_indices.size();
    if (active_dof_count == 0U) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR linear reference assembly requires at least one active DOF");
    }
    std::vector<std::uint32_t> global_to_reduced(
        graph.global_dof_count, std::numeric_limits<std::uint32_t>::max());
    auto reduced_dof = std::uint32_t {0U};
    for (std::size_t global_dof_index = 0U; global_dof_index < graph.global_dof_count;
         ++global_dof_index) {
        if (!constrained[global_dof_index]) {
            global_to_reduced[global_dof_index] = reduced_dof;
            ++reduced_dof;
        }
    }

    std::vector<std::uint64_t> structural_keys;
    auto recovery_value_count = std::size_t {0U};
    for (const auto& element : graph.elements) {
        std::vector<std::uint32_t> dofs;
        if (element.type == SA_ELEMENT_FRAME_3D) {
            dofs = frame_dofs(element);
            recovery_value_count += 12U;
        } else if (element.type == SA_ELEMENT_TRUSS_3D) {
            dofs = truss_dofs(element);
            recovery_value_count += 3U;
        } else {
            throw model_ir::Error(
                SA_ERR_INTERNAL,
                "projected ModelIR reference element kind became unsupported");
        }
        for (const auto global_row : dofs) {
            const auto row = global_to_reduced[global_row];
            if (row == std::numeric_limits<std::uint32_t>::max()) {
                continue;
            }
            for (const auto global_column : dofs) {
                const auto column = global_to_reduced[global_column];
                if (column == std::numeric_limits<std::uint32_t>::max()) {
                    continue;
                }
                if (structural_keys.size() == SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES) {
                    throw model_ir::Error(
                        SA_ERR_ANALYSIS_NOT_READY,
                        "ModelIR linear reference structure exceeds the bounded entry count");
                }
                structural_keys.push_back(
                    static_cast<std::uint64_t>(row)
                        * static_cast<std::uint64_t>(active_dof_count)
                    + column);
            }
        }
    }
    std::sort(structural_keys.begin(), structural_keys.end());
    structural_keys.erase(
        std::unique(structural_keys.begin(), structural_keys.end()), structural_keys.end());
    constexpr auto kSha256IdentityLength = std::size_t {71U};
    if (graph.content_hash.size() != kSha256IdentityLength
        || graph.semantic_hash.size() != kSha256IdentityLength
        || graph.provenance_hash.size() != kSha256IdentityLength) {
        throw model_ir::Error(SA_ERR_INTERNAL, "validated ModelIR identity length became invalid");
    }
    return {
        graph.global_dof_count,
        active_dof_count,
        active_dof_count + 1U,
        structural_keys.size(),
        graph.elements.size(),
        graph.elements.size() + 1U,
        recovery_value_count,
        kSha256IdentityLength,
    };
}

ModelIrLinearAssemblyResult assemble_model_ir_linear_reference(
    const model_ir::Model& model,
    const std::string_view load_pattern_id,
    const std::span<const double> displacement,
    const std::span<const double> direction) {
    if (load_pattern_id.empty()) {
        throw model_ir::Error(SA_ERR_INVALID_ARGUMENT, "ModelIR load-pattern selector is empty");
    }
    const auto graph = model.project_linear_reference_graph();
    if (graph.constrained_dof_indices.size() >= graph.global_dof_count) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR linear reference assembly requires at least one active DOF");
    }
    if (displacement.size() != graph.global_dof_count
        || direction.size() != graph.global_dof_count || !all_finite(displacement)
        || !all_finite(direction)) {
        throw model_ir::Error(
            SA_ERR_INVALID_ARGUMENT,
            "ModelIR assembly state vectors have invalid length or non-finite values");
    }
    for (const auto constrained_dof : graph.constrained_dof_indices) {
        if (displacement[constrained_dof] != 0.0 || direction[constrained_dof] != 0.0) {
            throw model_ir::Error(
                SA_ERR_INVALID_ARGUMENT,
                "ModelIR homogeneous constrained DOFs require zero state and direction");
        }
    }
    const auto pattern = std::find_if(
        graph.load_patterns.begin(),
        graph.load_patterns.end(),
        [load_pattern_id](const auto& candidate) { return candidate.id == load_pattern_id; });
    if (pattern == graph.load_patterns.end()) {
        throw model_ir::Error(
            SA_ERR_INVALID_ARGUMENT,
            "ModelIR load-pattern selector does not identify a bounded linear pattern");
    }

    std::vector<OwnedContribution> owned;
    owned.reserve(graph.elements.size());
    try {
        for (const auto& element : graph.elements) {
            const materials::ElasticIsotropic material {
                element.youngs_modulus_pa,
                element.poisson_ratio,
                element.density_kg_per_m3,
            };
            if (element.type == SA_ELEMENT_FRAME_3D) {
                auto dofs = frame_dofs(element);
                const auto local_displacement = gather<12U>(displacement, dofs);
                const auto local_direction = gather<12U>(direction, dofs);
                auto response = elements::evaluate_frame3d({
                    element.node_i_m,
                    element.node_j_m,
                    material,
                    element.area_m2,
                    element.iy_m4,
                    element.iz_m4,
                    element.torsional_constant_m4,
                    element.local_axis_rotation_rad,
                    local_displacement,
                    local_direction,
                });
                owned.push_back({
                    element.stable_index,
                    element.type,
                    std::move(dofs),
                    std::move(response),
                });
            } else if (element.type == SA_ELEMENT_TRUSS_3D) {
                auto dofs = truss_dofs(element);
                const auto local_displacement = gather<6U>(displacement, dofs);
                const auto local_direction = gather<6U>(direction, dofs);
                auto response = elements::evaluate_truss3d({
                    element.node_i_m,
                    element.node_j_m,
                    material,
                    element.area_m2,
                    local_displacement,
                    local_direction,
                });
                owned.push_back({
                    element.stable_index,
                    element.type,
                    std::move(dofs),
                    std::move(response),
                });
            } else {
                throw model_ir::Error(
                    SA_ERR_INTERNAL,
                    "projected ModelIR reference element kind became unsupported");
            }
        }
    } catch (const std::invalid_argument&) {
        throw model_ir::Error(
            SA_ERR_RESIDUAL_LIMIT,
            "ModelIR element response exceeds the bounded finite numerical domain");
    }

    std::vector<DenseElementContribution> contributions;
    contributions.reserve(owned.size());
    for (const auto& element : owned) {
        contributions.push_back({
            element.stable_index,
            element.dof_indices,
            element.response.tangent,
            element.response.consistent_mass,
            element.response.residual,
            element.response.jvp,
        });
    }
    CanonicalCsrAssemblyResult operator_result {};
    try {
        operator_result = assemble_reduced_csr_deterministic(
            graph.global_dof_count, contributions, graph.constrained_dof_indices);
    } catch (const std::overflow_error&) {
        throw model_ir::Error(
            SA_ERR_RESIDUAL_LIMIT,
            "ModelIR graph assembly exceeds the bounded finite numerical domain");
    } catch (const std::invalid_argument&) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR graph exceeds the bounded canonical assembly domain");
    }

    std::vector<double> full_external_load(graph.global_dof_count, 0.0);
    for (const auto& load : pattern->nodal_loads) {
        for (auto component = std::uint32_t {0U}; component < 6U; ++component) {
            full_external_load[global_dof(load.node_index, component)] +=
                load.components_si[component];
        }
    }
    if (!all_finite(full_external_load)) {
        throw model_ir::Error(
            SA_ERR_RESIDUAL_LIMIT,
            "ModelIR nodal-load accumulation exceeds the finite numerical domain");
    }

    ModelIrLinearAssemblyResult output;
    output.model_content_hash = graph.content_hash;
    output.model_semantic_hash = graph.semantic_hash;
    output.model_provenance_hash = graph.provenance_hash;
    output.load_pattern_id = pattern->id;
    output.load_pattern_index = pattern->stable_index;
    output.external_load.reserve(operator_result.active_dof_indices.size());
    output.equilibrium_residual.reserve(operator_result.active_dof_indices.size());
    for (std::size_t index = 0U; index < operator_result.active_dof_indices.size(); ++index) {
        const auto external = full_external_load[operator_result.active_dof_indices[index]];
        output.external_load.push_back(external == 0.0 ? 0.0 : external);
        const auto equilibrium = operator_result.residual[index] - external;
        if (!std::isfinite(equilibrium)) {
            throw model_ir::Error(
                SA_ERR_RESIDUAL_LIMIT,
                "ModelIR equilibrium residual exceeds the finite numerical domain");
        }
        output.equilibrium_residual.push_back(equilibrium == 0.0 ? 0.0 : equilibrium);
    }
    output.element_recovery.reserve(owned.size());
    for (auto& element : owned) {
        output.element_recovery.push_back({
            element.stable_index,
            element.element_type,
            std::move(element.response.recovery),
        });
    }
    output.operator_result = std::move(operator_result);
    return output;
}

}  // namespace structural::assembly
