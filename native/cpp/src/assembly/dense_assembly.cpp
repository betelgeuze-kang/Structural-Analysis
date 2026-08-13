#include "dense_assembly.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace structural::assembly {
namespace {

constexpr auto kMaximumContributionCount = std::size_t {1'000'000U};
constexpr auto kMaximumGlobalDofCount = std::size_t {1'000'000U};
constexpr auto kMaximumSparseStructuralEntries = std::size_t {100'000'000U};

[[nodiscard]] bool all_finite(const std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](const double value) {
        return std::isfinite(value);
    });
}

[[nodiscard]] std::vector<std::size_t> validate_and_order_contributions(
    const std::size_t global_dof_count,
    const std::span<const DenseElementContribution> contributions) {
    if (global_dof_count == 0U || global_dof_count > kMaximumGlobalDofCount) {
        throw std::invalid_argument("global DOF count is outside the bounded assembly domain");
    }
    if (contributions.size() > kMaximumContributionCount) {
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
    return order;
}

void normalize_signed_zeros(const std::span<double> values) {
    for (double& value : values) {
        if (value == 0.0) {
            value = 0.0;
        }
    }
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
    const auto order = validate_and_order_contributions(global_dof_count, contributions);

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

CanonicalCsrAssemblyResult assemble_reduced_csr_deterministic(
    const std::size_t global_dof_count,
    const std::span<const DenseElementContribution> contributions,
    const std::span<const std::uint32_t> constrained_dof_indices) {
    const auto order = validate_and_order_contributions(global_dof_count, contributions);
    std::vector<bool> constrained(global_dof_count, false);
    for (const auto dof : constrained_dof_indices) {
        if (dof >= global_dof_count) {
            throw std::invalid_argument("constrained DOF index is out of range");
        }
        if (constrained[dof]) {
            throw std::invalid_argument("constrained DOF indices must be unique");
        }
        constrained[dof] = true;
    }

    constexpr auto inactive = std::numeric_limits<std::uint32_t>::max();
    std::vector<std::uint32_t> global_to_reduced(global_dof_count, inactive);
    std::vector<std::uint32_t> active_dof_indices;
    active_dof_indices.reserve(global_dof_count - constrained_dof_indices.size());
    for (std::size_t global_dof = 0U; global_dof < global_dof_count; ++global_dof) {
        if (constrained[global_dof]) {
            continue;
        }
        const auto reduced_dof = static_cast<std::uint32_t>(active_dof_indices.size());
        global_to_reduced[global_dof] = reduced_dof;
        active_dof_indices.push_back(static_cast<std::uint32_t>(global_dof));
    }
    if (active_dof_indices.empty()) {
        throw std::invalid_argument("constraint reduction must retain at least one active DOF");
    }

    const auto reduced_order = active_dof_indices.size();
    std::vector<std::uint64_t> structural_keys;
    for (const auto contribution_index : order) {
        const auto& contribution = contributions[contribution_index];
        for (const auto global_row : contribution.dof_indices) {
            const auto reduced_row = global_to_reduced[global_row];
            if (reduced_row == inactive) {
                continue;
            }
            for (const auto global_column : contribution.dof_indices) {
                const auto reduced_column = global_to_reduced[global_column];
                if (reduced_column == inactive) {
                    continue;
                }
                if (structural_keys.size() == kMaximumSparseStructuralEntries) {
                    throw std::invalid_argument(
                        "sparse assembly structural entry count exceeds the bounded contract");
                }
                structural_keys.push_back(
                    static_cast<std::uint64_t>(reduced_row)
                    * static_cast<std::uint64_t>(reduced_order)
                    + reduced_column);
            }
        }
    }
    std::sort(structural_keys.begin(), structural_keys.end());
    structural_keys.erase(
        std::unique(structural_keys.begin(), structural_keys.end()), structural_keys.end());

    std::vector<std::uint64_t> row_offsets(reduced_order + 1U, 0U);
    std::vector<std::uint32_t> column_indices;
    column_indices.reserve(structural_keys.size());
    for (const auto key : structural_keys) {
        const auto row = static_cast<std::size_t>(key / reduced_order);
        const auto column = static_cast<std::uint32_t>(key % reduced_order);
        ++row_offsets[row + 1U];
        column_indices.push_back(column);
    }
    std::partial_sum(row_offsets.begin(), row_offsets.end(), row_offsets.begin());

    CanonicalCsrAssemblyResult output {
        global_dof_count,
        std::move(active_dof_indices),
        std::move(row_offsets),
        std::move(column_indices),
        std::vector<double>(structural_keys.size(), 0.0),
        std::vector<double>(structural_keys.size(), 0.0),
        std::vector<double>(reduced_order, 0.0),
        std::vector<double>(reduced_order, 0.0),
    };
    for (const auto contribution_index : order) {
        const auto& contribution = contributions[contribution_index];
        const auto local_dof_count = contribution.dof_indices.size();
        for (std::size_t local_row = 0U; local_row < local_dof_count; ++local_row) {
            const auto reduced_row = global_to_reduced[contribution.dof_indices[local_row]];
            if (reduced_row == inactive) {
                continue;
            }
            output.residual[reduced_row] += contribution.residual[local_row];
            output.jvp[reduced_row] += contribution.jvp[local_row];
            for (std::size_t local_column = 0U; local_column < local_dof_count; ++local_column) {
                const auto reduced_column =
                    global_to_reduced[contribution.dof_indices[local_column]];
                if (reduced_column == inactive) {
                    continue;
                }
                const auto key = static_cast<std::uint64_t>(reduced_row)
                    * static_cast<std::uint64_t>(reduced_order)
                    + reduced_column;
                const auto found = std::lower_bound(
                    structural_keys.begin(), structural_keys.end(), key);
                if (found == structural_keys.end() || *found != key) {
                    throw std::logic_error("sparse assembly structure is internally inconsistent");
                }
                const auto output_offset =
                    static_cast<std::size_t>(found - structural_keys.begin());
                const auto local_offset = local_row * local_dof_count + local_column;
                output.tangent[output_offset] += contribution.tangent[local_offset];
                output.consistent_mass[output_offset] +=
                    contribution.consistent_mass[local_offset];
            }
        }
    }
    normalize_signed_zeros(output.tangent);
    normalize_signed_zeros(output.consistent_mass);
    normalize_signed_zeros(output.residual);
    normalize_signed_zeros(output.jvp);
    if (!all_finite(output.tangent) || !all_finite(output.consistent_mass)
        || !all_finite(output.residual) || !all_finite(output.jvp)) {
        throw std::overflow_error(
            "sparse assembly accumulation exceeds the finite numerical domain");
    }
    return output;
}

}  // namespace structural::assembly
