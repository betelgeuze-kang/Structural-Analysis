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

/// Bounded C1 output for one explicit linear-static ModelIR load pattern.
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

/// Project a validated typed ModelIR graph through the reference frame/truss sources and assemble
/// one canonical homogeneous-constraint-reduced operator.
[[nodiscard]] ModelIrLinearAssemblyResult assemble_model_ir_linear_reference(
    const model_ir::Model& model,
    std::string_view load_pattern_id,
    std::span<const double> displacement,
    std::span<const double> direction);

}  // namespace structural::assembly

#endif
