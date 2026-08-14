#ifndef STRUCTURAL_ASSEMBLY_MODEL_IR_ASSEMBLY_HPP
#define STRUCTURAL_ASSEMBLY_MODEL_IR_ASSEMBLY_HPP

#include "dense_assembly.hpp"
#include "../model_ir/model_ir.hpp"

#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace structural::assembly {

struct ModelIrElementRecovery final {
    std::uint64_t stable_index {};
    std::uint32_t element_type {};
    std::vector<double> values;
};

struct ModelIrLinearAssemblySizes final {
    std::size_t global_dof_count {};
    std::size_t active_dof_count {};
    std::size_t row_offset_count {};
    std::size_t structural_entry_count {};
    std::size_t recovery_record_count {};
    std::size_t recovery_offset_count {};
    std::size_t recovery_value_count {};
    std::size_t model_identity_length {};
};

/// Bounded C1 output for one explicit linear-static ModelIR load-case selector.
///
/// `operator_result.residual` is the assembled internal force. `external_load` and
/// `equilibrium_residual = internal - external` use the same reduced active-DOF order.
struct ModelIrLinearAssemblyResult final {
    std::string model_content_hash;
    std::string model_semantic_hash;
    std::string model_provenance_hash;
    std::string load_pattern_id;
    std::uint64_t load_pattern_index {};
    CanonicalCsrAssemblyResult operator_result {};
    std::vector<double> external_load;
    std::vector<double> equilibrium_residual;
    std::vector<ModelIrElementRecovery> element_recovery;
};

/// Return exact caller-owned output lengths for the immutable bounded ModelIR graph.
[[nodiscard]] ModelIrLinearAssemblySizes model_ir_linear_reference_sizes(
    const model_ir::Model& model);

/// Project a validated typed ModelIR graph through the reference frame/truss sources and assemble
/// one canonical homogeneous-constraint-reduced operator. The frozen ABI v1.13
/// `load_pattern_id` selector accepts either one pattern or one bounded two-to-64-term linear
/// combination of unique direct patterns; nested or ambiguous selectors fail closed.
[[nodiscard]] ModelIrLinearAssemblyResult assemble_model_ir_linear_reference(
    const model_ir::Model& model,
    std::string_view load_pattern_id,
    std::span<const double> displacement,
    std::span<const double> direction);

}  // namespace structural::assembly

#endif
