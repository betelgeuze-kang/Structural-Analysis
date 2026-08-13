#ifndef STRUCTURAL_ASSEMBLY_DENSE_ASSEMBLY_HPP
#define STRUCTURAL_ASSEMBLY_DENSE_ASSEMBLY_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace structural::assembly {

struct DenseElementContribution {
    std::uint64_t stable_index;
    std::span<const std::uint32_t> dof_indices;
    std::span<const double> tangent;
    std::span<const double> consistent_mass;
    std::span<const double> residual;
    std::span<const double> jvp;
};

struct DenseAssemblyResult {
    std::size_t global_dof_count;
    std::vector<double> tangent;
    std::vector<double> consistent_mass;
    std::vector<double> residual;
    std::vector<double> jvp;
};

/// Canonical CSR projection of one stable-order assembly after zero-valued Dirichlet DOFs are
/// removed. Column indices address the reduced `active_dof_indices` order.
struct CanonicalCsrAssemblyResult {
    std::size_t global_dof_count;
    std::vector<std::uint32_t> active_dof_indices;
    std::vector<std::uint64_t> row_offsets;
    std::vector<std::uint32_t> column_indices;
    std::vector<double> tangent;
    std::vector<double> consistent_mass;
    std::vector<double> residual;
    std::vector<double> jvp;
};

[[nodiscard]] DenseAssemblyResult assemble_dense_deterministic(
    std::size_t global_dof_count,
    std::span<const DenseElementContribution> contributions);

/// Deterministically assemble and reduce caller-supplied element contributions to canonical CSR.
///
/// Constrained DOFs are homogeneous Dirichlet eliminations. The returned active mapping is sorted
/// by global DOF, every CSR row has strictly increasing reduced columns, structural zero entries
/// are retained, and contributions accumulate in unique `stable_index` order.
[[nodiscard]] CanonicalCsrAssemblyResult assemble_reduced_csr_deterministic(
    std::size_t global_dof_count,
    std::span<const DenseElementContribution> contributions,
    std::span<const std::uint32_t> constrained_dof_indices);

}  // namespace structural::assembly

#endif
