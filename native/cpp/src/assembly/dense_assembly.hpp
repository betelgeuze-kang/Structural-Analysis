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

[[nodiscard]] DenseAssemblyResult assemble_dense_deterministic(
    std::size_t global_dof_count,
    std::span<const DenseElementContribution> contributions);

}  // namespace structural::assembly

#endif
