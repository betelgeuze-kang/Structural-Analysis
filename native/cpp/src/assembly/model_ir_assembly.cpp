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

struct SelectedLoadPattern final {
    const model_ir::LinearReferenceLoadPattern* pattern {};
    double factor {};
};

struct SelectedLoadCase final {
    std::string_view id;
    std::uint64_t stable_index {};
    std::vector<SelectedLoadPattern> patterns;
};

constexpr double kStandardGravityMPerS2 = 9.80665;

[[nodiscard]] const model_ir::LinearReferenceLoadPattern* find_load_pattern(
    const model_ir::LinearReferenceGraph& graph,
    const std::string_view id) {
    const auto found = std::find_if(
        graph.load_patterns.begin(),
        graph.load_patterns.end(),
        [id](const auto& candidate) { return candidate.id == id; });
    return found == graph.load_patterns.end() ? nullptr : &*found;
}

[[nodiscard]] const model_ir::LinearReferenceLoadCombination* find_load_combination(
    const model_ir::LinearReferenceGraph& graph,
    const std::string_view id) {
    const auto found = std::find_if(
        graph.load_combinations.begin(),
        graph.load_combinations.end(),
        [id](const auto& candidate) { return candidate.id == id; });
    return found == graph.load_combinations.end() ? nullptr : &*found;
}

void require_bounded_combination_terms(
    const model_ir::LinearReferenceLoadCombination& combination,
    const char* const profile) {
    if (combination.terms.size() < 2U
        || combination.terms.size() > SA_MODEL_IR_LINEAR_MAX_DIRECT_COMBINATION_TERMS) {
        throw model_ir::Error(SA_ERR_ANALYSIS_NOT_READY, profile);
    }
}

void append_nested_combination_patterns(
    const model_ir::LinearReferenceGraph& graph,
    const model_ir::LinearReferenceLoadCombination& combination,
    const double parent_factor,
    const std::uint64_t depth,
    std::uint64_t& expanded_term_count,
    std::vector<const model_ir::LinearReferenceLoadCombination*>& active,
    std::vector<SelectedLoadPattern>& patterns) {
    if (depth > SA_MODEL_IR_LINEAR_MAX_NESTED_COMBINATION_DEPTH) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR nested linear combination exceeds the maximum depth of eight");
    }
    if (std::find(active.begin(), active.end(), &combination) != active.end()) {
        throw model_ir::Error(
            SA_ERR_ANALYSIS_NOT_READY,
            "ModelIR nested linear combination contains a cycle");
    }
    require_bounded_combination_terms(
        combination,
        "ModelIR nested linear assembly requires between two and 64 terms per combination");
    active.push_back(&combination);
    for (const auto& term : combination.terms) {
        if (!std::isfinite(term.factor) || term.factor == 0.0) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR nested linear assembly requires finite nonzero combination factors");
        }
        const auto scaled_factor = parent_factor * term.factor;
        if (!std::isfinite(scaled_factor) || scaled_factor == 0.0) {
            throw model_ir::Error(
                SA_ERR_RESIDUAL_LIMIT,
                "ModelIR nested combination factor propagation exceeds the finite numerical domain");
        }
        if (term.ref_kind == SA_LOAD_REF_COMBINATION) {
            const auto* const nested = find_load_combination(graph, term.ref_id);
            if (nested == nullptr) {
                throw model_ir::Error(
                    SA_ERR_INTERNAL,
                    "validated ModelIR nested combination reference became unavailable");
            }
            append_nested_combination_patterns(
                graph,
                *nested,
                scaled_factor,
                depth + 1U,
                expanded_term_count,
                active,
                patterns);
            continue;
        }
        if (term.ref_kind != SA_LOAD_REF_PATTERN) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR nested linear assembly encountered an unsupported reference kind");
        }
        ++expanded_term_count;
        if (expanded_term_count > SA_MODEL_IR_LINEAR_MAX_EXPANDED_COMBINATION_TERMS) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR nested linear combination expands beyond 64 pattern terms");
        }
        const auto* const referenced = find_load_pattern(graph, term.ref_id);
        if (referenced == nullptr) {
            throw model_ir::Error(
                SA_ERR_INTERNAL,
                "validated ModelIR nested combination pattern reference became unavailable");
        }
        const auto prior = std::find_if(
            patterns.begin(),
            patterns.end(),
            [referenced](const auto& candidate) { return candidate.pattern == referenced; });
        if (prior == patterns.end()) {
            patterns.push_back({referenced, scaled_factor});
            continue;
        }
        const auto accumulated = prior->factor + scaled_factor;
        if (!std::isfinite(accumulated)) {
            throw model_ir::Error(
                SA_ERR_RESIDUAL_LIMIT,
                "ModelIR nested combination factor accumulation exceeds the finite numerical domain");
        }
        prior->factor = accumulated == 0.0 ? 0.0 : accumulated;
    }
    active.pop_back();
}

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

[[nodiscard]] SelectedLoadCase select_load_case(
    const model_ir::LinearReferenceGraph& graph,
    const std::string_view selector_id) {
    const auto* const pattern = find_load_pattern(graph, selector_id);
    const auto* const combination = find_load_combination(graph, selector_id);
    if (pattern != nullptr && combination != nullptr) {
        throw model_ir::Error(
            SA_ERR_INVALID_ARGUMENT,
            "ModelIR load-case selector is ambiguous across patterns and combinations");
    }
    if (pattern != nullptr) {
        return {pattern->id, pattern->stable_index, {{pattern, 1.0}}};
    }
    if (combination == nullptr) {
        throw model_ir::Error(
            SA_ERR_INVALID_ARGUMENT,
            "ModelIR load-case selector does not identify a bounded linear pattern or combination");
    }
    require_bounded_combination_terms(
        *combination,
        "ModelIR linear reference assembly requires between two and 64 direct combination terms");

    SelectedLoadCase selected {combination->id, combination->stable_index, {}};
    const auto nested = std::any_of(
        combination->terms.begin(), combination->terms.end(), [](const auto& term) {
            return term.ref_kind == SA_LOAD_REF_COMBINATION;
        });
    if (nested) {
        auto expanded_term_count = std::uint64_t {0U};
        std::vector<const model_ir::LinearReferenceLoadCombination*> active;
        append_nested_combination_patterns(
            graph, *combination, 1.0, 1U, expanded_term_count, active, selected.patterns);
        selected.patterns.erase(
            std::remove_if(
                selected.patterns.begin(),
                selected.patterns.end(),
                [](const auto& term) { return term.factor == 0.0; }),
            selected.patterns.end());
        if (selected.patterns.size() < 2U
            || selected.patterns.size()
                > SA_MODEL_IR_LINEAR_MAX_EXPANDED_COMBINATION_TERMS) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR nested linear combination must resolve to between two and 64 nonzero unique patterns");
        }
        return selected;
    }

    selected.patterns.reserve(combination->terms.size());
    for (const auto& term : combination->terms) {
        if (term.ref_kind != SA_LOAD_REF_PATTERN || !std::isfinite(term.factor)
            || term.factor == 0.0) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR linear reference assembly requires finite nonzero direct-pattern combination terms");
        }
        const auto* const referenced = find_load_pattern(graph, term.ref_id);
        if (referenced == nullptr) {
            throw model_ir::Error(
                SA_ERR_INTERNAL,
                "validated ModelIR combination pattern reference became unavailable");
        }
        if (std::any_of(
                selected.patterns.begin(),
                selected.patterns.end(),
                [referenced](const auto& prior) { return prior.pattern == referenced; })) {
            throw model_ir::Error(
                SA_ERR_ANALYSIS_NOT_READY,
                "ModelIR linear reference assembly requires unique direct combination patterns");
        }
        selected.patterns.push_back({referenced, term.factor});
    }
    return selected;
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
        throw model_ir::Error(SA_ERR_INVALID_ARGUMENT, "ModelIR load-case selector is empty");
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
    if (graph.constrained_dof_values.size() != graph.constrained_dof_indices.size()) {
        throw model_ir::Error(
            SA_ERR_INTERNAL,
            "ModelIR constrained DOF values became inconsistent with the reduced graph");
    }
    for (std::size_t index = 0U; index < graph.constrained_dof_indices.size(); ++index) {
        const auto constrained_dof = graph.constrained_dof_indices[index];
        if (displacement[constrained_dof] != graph.constrained_dof_values[index]
            || direction[constrained_dof] != 0.0) {
            throw model_ir::Error(
                SA_ERR_INVALID_ARGUMENT,
                "ModelIR constrained DOFs require the exact prescribed state and zero direction");
        }
    }
    const auto load_case = select_load_case(graph, load_pattern_id);

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
                    element.offset_i_global_m,
                    element.offset_j_global_m,
                    element.releases_i,
                    element.releases_j,
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
    std::sort(owned.begin(), owned.end(), [](const auto& left, const auto& right) {
        return left.stable_index < right.stable_index;
    });
    std::vector<double> full_internal_force(graph.global_dof_count, 0.0);
    for (const auto& element : owned) {
        contributions.push_back({
            element.stable_index,
            element.dof_indices,
            element.response.tangent,
            element.response.consistent_mass,
            element.response.residual,
            element.response.jvp,
        });
        for (std::size_t local_dof = 0U; local_dof < element.dof_indices.size(); ++local_dof) {
            const auto global_dof_index = element.dof_indices[local_dof];
            const auto accumulated = full_internal_force[global_dof_index]
                + element.response.residual[local_dof];
            if (!std::isfinite(accumulated)) {
                throw model_ir::Error(
                    SA_ERR_RESIDUAL_LIMIT,
                    "ModelIR full internal-force accumulation exceeds the finite numerical domain");
            }
            full_internal_force[global_dof_index] = accumulated == 0.0 ? 0.0 : accumulated;
        }
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
    for (const auto& selected : load_case.patterns) {
        for (const auto& load : selected.pattern->nodal_loads) {
            for (auto component = std::uint32_t {0U}; component < 6U; ++component) {
                const auto scaled = selected.factor * load.components_si[component];
                const auto index = global_dof(load.node_index, component);
                const auto accumulated = full_external_load[index] + scaled;
                if (!std::isfinite(scaled) || !std::isfinite(accumulated)) {
                    throw model_ir::Error(
                        SA_ERR_RESIDUAL_LIMIT,
                        "ModelIR load-case accumulation exceeds the finite numerical domain");
                }
                full_external_load[index] = accumulated;
            }
        }
        for (const auto& load : selected.pattern->member_distributed_loads) {
            const auto source = std::find_if(
                graph.elements.begin(),
                graph.elements.end(),
                [&load](const auto& candidate) {
                    return candidate.stable_index == load.element_index;
                });
            const auto contribution = std::find_if(
                owned.begin(),
                owned.end(),
                [&load](const auto& candidate) {
                    return candidate.stable_index == load.element_index;
                });
            if (source == graph.elements.end() || contribution == owned.end()
                || source->type != SA_ELEMENT_FRAME_3D
                || contribution->dof_indices.size() != 12U
                || contribution->response.recovery.size() != 12U) {
                throw model_ir::Error(
                    SA_ERR_INTERNAL,
                    "validated ModelIR Frame3D member-load target became unavailable");
            }
            const materials::ElasticIsotropic material {
                source->youngs_modulus_pa,
                source->poisson_ratio,
                source->density_kg_per_m3,
            };
            elements::Frame3dUniformDistributedLoadResponse member_response;
            try {
                member_response = elements::evaluate_frame3d_uniform_distributed_load({
                    source->node_i_m,
                    source->node_j_m,
                    material,
                    source->area_m2,
                    source->iy_m4,
                    source->iz_m4,
                    source->torsional_constant_m4,
                    source->local_axis_rotation_rad,
                    load.components_si,
                    source->offset_i_global_m,
                    source->offset_j_global_m,
                    source->releases_i,
                    source->releases_j,
                });
            } catch (const std::invalid_argument&) {
                throw model_ir::Error(
                    SA_ERR_RESIDUAL_LIMIT,
                    "ModelIR Frame3D member distributed-load projection exceeds the bounded finite numerical domain");
            }
            for (std::size_t local_dof = 0U; local_dof < 12U; ++local_dof) {
                const auto scaled_external =
                    selected.factor * member_response.global_equivalent_load[local_dof];
                const auto global_index = contribution->dof_indices[local_dof];
                const auto accumulated_external =
                    full_external_load[global_index] + scaled_external;
                const auto scaled_recovery =
                    selected.factor * member_response.local_recovery_equivalent[local_dof];
                const auto recovered =
                    contribution->response.recovery[local_dof] - scaled_recovery;
                if (!std::isfinite(scaled_external) || !std::isfinite(accumulated_external)
                    || !std::isfinite(scaled_recovery) || !std::isfinite(recovered)) {
                    throw model_ir::Error(
                        SA_ERR_RESIDUAL_LIMIT,
                        "ModelIR Frame3D member distributed-load accumulation exceeds the finite numerical domain");
                }
                full_external_load[global_index] =
                    accumulated_external == 0.0 ? 0.0 : accumulated_external;
                contribution->response.recovery[local_dof] =
                    recovered == 0.0 ? 0.0 : recovered;
            }
        }
        std::array<double, 3> gravity_acceleration {};
        for (std::size_t axis = 0U; axis < gravity_acceleration.size(); ++axis) {
            gravity_acceleration[axis] = selected.factor
                * selected.pattern->self_weight[axis] * kStandardGravityMPerS2;
            if (!std::isfinite(gravity_acceleration[axis])) {
                throw model_ir::Error(
                    SA_ERR_RESIDUAL_LIMIT,
                    "ModelIR self-weight factor propagation exceeds the finite numerical domain");
            }
        }
        if (std::any_of(
                gravity_acceleration.begin(),
                gravity_acceleration.end(),
                [](const double value) { return value != 0.0; })) {
            for (const auto& element : owned) {
                const auto dimension = element.dof_indices.size();
                if (element.response.consistent_mass.size() != dimension * dimension) {
                    throw model_ir::Error(
                        SA_ERR_INTERNAL,
                        "ModelIR element mass shape became invalid during self-weight assembly");
                }
                for (std::size_t row = 0U; row < dimension; ++row) {
                    double equivalent_load = 0.0;
                    for (std::size_t column = 0U; column < dimension; ++column) {
                        const auto component = element.dof_indices[column] % 6U;
                        const auto acceleration = component < 3U
                            ? gravity_acceleration[component]
                            : 0.0;
                        const auto contribution =
                            element.response.consistent_mass[row * dimension + column]
                            * acceleration;
                        equivalent_load += contribution;
                        if (!std::isfinite(contribution) || !std::isfinite(equivalent_load)) {
                            throw model_ir::Error(
                                SA_ERR_RESIDUAL_LIMIT,
                                "ModelIR self-weight equivalent-load assembly exceeds the finite numerical domain");
                        }
                    }
                    const auto global_index = element.dof_indices[row];
                    const auto accumulated = full_external_load[global_index] + equivalent_load;
                    if (!std::isfinite(accumulated)) {
                        throw model_ir::Error(
                            SA_ERR_RESIDUAL_LIMIT,
                            "ModelIR self-weight accumulation exceeds the finite numerical domain");
                    }
                    full_external_load[global_index] = accumulated == 0.0 ? 0.0 : accumulated;
                }
            }
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
    output.load_pattern_id = load_case.id;
    output.load_pattern_index = load_case.stable_index;
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
    output.constrained_dof_indices.assign(
        graph.constrained_dof_indices.begin(), graph.constrained_dof_indices.end());
    std::sort(output.constrained_dof_indices.begin(), output.constrained_dof_indices.end());
    output.constrained_internal_force.reserve(output.constrained_dof_indices.size());
    output.constrained_external_load.reserve(output.constrained_dof_indices.size());
    output.reactions.reserve(output.constrained_dof_indices.size());
    for (const auto constrained_dof : output.constrained_dof_indices) {
        const auto internal = full_internal_force[constrained_dof];
        const auto external = full_external_load[constrained_dof];
        const auto reaction = internal - external;
        if (!std::isfinite(reaction)) {
            throw model_ir::Error(
                SA_ERR_RESIDUAL_LIMIT,
                "ModelIR constrained reaction exceeds the finite numerical domain");
        }
        output.constrained_internal_force.push_back(internal == 0.0 ? 0.0 : internal);
        output.constrained_external_load.push_back(external == 0.0 ? 0.0 : external);
        output.reactions.push_back(reaction == 0.0 ? 0.0 : reaction);
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
