#include "dense_assembly.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace structural::assembly {
namespace {

[[nodiscard]] bool all_finite(const std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](const double value) {
        return std::isfinite(value);
    });
}

}  // namespace

DenseAssemblyResult assemble_dense_deterministic(
    const std::size_t global_dof_count,
    const std::span<const DenseElementContribution> contributions) {
    constexpr auto max_dense_matrix_entries = std::size_t {16U * 1024U * 1024U};
    if (global_dof_count == 0U
        || global_dof_count > std::numeric_limits<std::size_t>::max() / global_dof_count
        || global_dof_count * global_dof_count > max_dense_matrix_entries) {
        throw std::invalid_argument("global DOF count is invalid or overflows a dense matrix");
    }
    if (contributions.size() > 1000000U) {
        throw std::invalid_argument("element contribution count exceeds the bounded contract");
    }
    std::vector<std::size_t> order(contributions.size(), 0U);
    std::iota(order.begin(), order.end(), 0U);
    std::sort(order.begin(), order.end(), [&contributions](const auto left, const auto right) {
        return contributions[left].stable_index < contributions[right].stable_index;
    });

    auto prior_index = std::uint64_t {0U};
    auto has_prior = false;
    for (const auto contribution_index : order) {
        const auto& contribution = contributions[contribution_index];
        if (has_prior && contribution.stable_index == prior_index) {
            throw std::invalid_argument("element stable indices must be unique");
        }
        prior_index = contribution.stable_index;
        has_prior = true;
        const auto local_dof_count = contribution.dof_indices.size();
        if (local_dof_count == 0U
            || local_dof_count > std::numeric_limits<std::size_t>::max() / local_dof_count
            || contribution.tangent.size() != local_dof_count * local_dof_count
            || contribution.consistent_mass.size() != local_dof_count * local_dof_count
            || contribution.residual.size() != local_dof_count
            || contribution.jvp.size() != local_dof_count
            || !all_finite(contribution.tangent)
            || !all_finite(contribution.consistent_mass)
            || !all_finite(contribution.residual)
            || !all_finite(contribution.jvp)) {
            throw std::invalid_argument("element contribution shapes or values are invalid");
        }
        std::vector<std::uint32_t> sorted_dofs(
            contribution.dof_indices.begin(), contribution.dof_indices.end());
        std::sort(sorted_dofs.begin(), sorted_dofs.end());
        if (std::adjacent_find(sorted_dofs.begin(), sorted_dofs.end()) != sorted_dofs.end()) {
            throw std::invalid_argument("one element contribution contains duplicate DOF indices");
        }
        if (sorted_dofs.back() >= global_dof_count) {
            throw std::invalid_argument("element contribution references an out-of-range DOF");
        }
    }

    const auto matrix_size = global_dof_count * global_dof_count;
    DenseAssemblyResult output {
        global_dof_count,
        std::vector<double>(matrix_size, 0.0),
        std::vector<double>(matrix_size, 0.0),
        std::vector<double>(global_dof_count, 0.0),
        std::vector<double>(global_dof_count, 0.0),
    };
    for (const auto contribution_index : order) {
        const auto& contribution = contributions[contribution_index];
        const auto local_dof_count = contribution.dof_indices.size();
        for (std::size_t local_row = 0U; local_row < local_dof_count; ++local_row) {
            const auto global_row = contribution.dof_indices[local_row];
            output.residual[global_row] += contribution.residual[local_row];
            output.jvp[global_row] += contribution.jvp[local_row];
            for (std::size_t local_column = 0U; local_column < local_dof_count; ++local_column) {
                const auto global_column = contribution.dof_indices[local_column];
                const auto local_offset = local_row * local_dof_count + local_column;
                const auto global_offset = global_row * global_dof_count + global_column;
                output.tangent[global_offset] += contribution.tangent[local_offset];
                output.consistent_mass[global_offset] +=
                    contribution.consistent_mass[local_offset];
            }
        }
    }
    if (!all_finite(output.tangent) || !all_finite(output.consistent_mass)
        || !all_finite(output.residual) || !all_finite(output.jvp)) {
        throw std::overflow_error("dense assembly accumulation exceeds the finite numerical domain");
    }
    return output;
}

}  // namespace structural::assembly
