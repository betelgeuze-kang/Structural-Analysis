#include "full_residual.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

namespace structural::solver_cpu {
namespace {

constexpr std::uint32_t kCpuBackend = 1U;

[[nodiscard]] bool checked_product(
    const std::size_t left,
    const std::size_t right,
    std::size_t& output) noexcept {
    if (left != 0U && right > std::numeric_limits<std::size_t>::max() / left) {
        return false;
    }
    output = left * right;
    return true;
}

void require_finite(const std::span<const double> values, const std::string_view label) {
    if (!std::all_of(values.begin(), values.end(), [](const double value) {
            return std::isfinite(value);
        })) {
        throw std::invalid_argument(std::string(label) + " contains a non-finite value");
    }
}

void validate_csr(
    const std::span<const std::uint64_t> row_offsets,
    const std::span<const std::uint64_t> column_indices,
    const std::span<const double> values,
    const std::size_t order,
    const std::size_t nonzeros,
    const std::string_view label) {
    if (row_offsets.size() != order + 1U || column_indices.size() != nonzeros
        || values.size() != nonzeros || row_offsets.front() != 0U
        || row_offsets.back() != nonzeros) {
        throw std::invalid_argument(std::string(label) + " CSR dimensions are invalid");
    }
    require_finite(values, label);
    for (std::size_t row = 0U; row < order; ++row) {
        const auto begin = row_offsets[row];
        const auto end = row_offsets[row + 1U];
        if (begin > end || end > nonzeros) {
            throw std::invalid_argument(std::string(label) + " CSR offsets are not monotonic");
        }
        for (auto offset = begin; offset < end; ++offset) {
            if (column_indices[static_cast<std::size_t>(offset)] >= order) {
                throw std::invalid_argument(std::string(label) + " CSR column is out of range");
            }
        }
    }
}

class CpuFullResidualContext final : public FullResidualContext {
  public:
    explicit CpuFullResidualContext(FullResidualOperator operator_data)
        : operator_(std::move(operator_data)) {}

    [[nodiscard]] std::uint32_t execution_backend() const noexcept override {
        return kCpuBackend;
    }

    [[nodiscard]] std::int32_t device_id() const noexcept override { return -1; }

    [[nodiscard]] std::string_view device_name() const noexcept override {
        return "deterministic-cpu-fp64";
    }

    [[nodiscard]] const FullResidualOperator& operator_data() const noexcept override {
        return operator_;
    }

    [[nodiscard]] FullResidualMetrics creation_metrics() const noexcept override { return {}; }

    [[nodiscard]] FullResidualMetrics evaluate(
        const std::span<const double> states,
        const std::size_t batch_size,
        const std::uint32_t repetitions,
        const std::span<double> residual) override {
        validate_full_residual_evaluation(
            operator_, states, batch_size, repetitions, residual.size());
        const auto state_count = batch_size * operator_.order;
        const auto output_count = batch_size * operator_.free_dof_count;

        const bool reused = state_count <= state_capacity_ && output_count <= output_capacity_;
        state_capacity_ = std::max(state_capacity_, state_count);
        output_capacity_ = std::max(output_capacity_, output_count);
        const auto started = std::chrono::steady_clock::now();
        for (std::uint32_t repetition = 0U; repetition < repetitions; ++repetition) {
            for (std::size_t batch = 0U; batch < batch_size; ++batch) {
                const auto state = states.subspan(batch * operator_.order, operator_.order);
                for (std::size_t free_index = 0U; free_index < operator_.free_dof_count;
                     ++free_index) {
                    const auto row = static_cast<std::size_t>(operator_.free_dofs[free_index]);
                    double value = 0.0;
                    for (std::size_t element = 0U; element < operator_.frame_element_count;
                         ++element) {
                        const auto dof_base = element * kFullResidualFrameDofCount;
                        const auto matrix_base = element * kFullResidualFrameMatrixCount;
                        for (std::size_t local_row = 0U;
                             local_row < kFullResidualFrameDofCount;
                             ++local_row) {
                            if (operator_.frame_dofs[dof_base + local_row] != row) {
                                continue;
                            }
                            double local_value = 0.0;
                            const auto stiffness_row = matrix_base
                                + local_row * kFullResidualFrameDofCount;
                            for (std::size_t local_column = 0U;
                                 local_column < kFullResidualFrameDofCount;
                                 ++local_column) {
                                const auto column = static_cast<std::size_t>(
                                    operator_.frame_dofs[dof_base + local_column]);
                                local_value += operator_.frame_stiffness[
                                                   stiffness_row + local_column]
                                    * state[column];
                            }
                            value += local_value;
                        }
                    }
                    for (auto offset = operator_.shell_row_offsets[row];
                         offset < operator_.shell_row_offsets[row + 1U];
                         ++offset) {
                        const auto index = static_cast<std::size_t>(offset);
                        value += operator_.shell_values[index]
                            * state[static_cast<std::size_t>(operator_.shell_column_indices[index])];
                    }
                    for (auto offset = operator_.spring_row_offsets[row];
                         offset < operator_.spring_row_offsets[row + 1U];
                         ++offset) {
                        const auto index = static_cast<std::size_t>(offset);
                        value += operator_.spring_values[index]
                            * state[static_cast<std::size_t>(operator_.spring_column_indices[index])];
                    }
                    residual[batch * operator_.free_dof_count + free_index] =
                        value - operator_.external_force[row];
                }
            }
        }
        const auto stopped = std::chrono::steady_clock::now();
        double output_abs_sum = 0.0;
        double output_max_abs = 0.0;
        for (const double value : residual) {
            if (!std::isfinite(value)) {
                throw std::invalid_argument("full residual result is non-finite");
            }
            output_abs_sum += std::abs(value);
            output_max_abs = std::max(output_max_abs, std::abs(value));
        }
        const double elapsed = std::chrono::duration<double, std::milli>(stopped - started).count();
        return {
            reused,
            false,
            0U,
            0U,
            0U,
            0U,
            0U,
            0U,
            0U,
            0U,
            0U,
            0U,
            elapsed,
            elapsed / static_cast<double>(repetitions),
            output_abs_sum,
            output_max_abs,
        };
    }

  private:
    FullResidualOperator operator_;
    std::size_t state_capacity_ {0U};
    std::size_t output_capacity_ {0U};
};

}  // namespace

FullResidualOperator make_full_residual_operator(const FullResidualOperatorInput& input) {
    std::size_t frame_dof_count = 0U;
    std::size_t frame_matrix_count = 0U;
    if (input.frame_element_count == 0U
        || input.frame_element_count > kFullResidualMaximumFrameCount || input.order == 0U
        || input.order > kFullResidualMaximumOrder || input.free_dof_count == 0U
        || input.free_dof_count > input.order
        || input.shell_nonzeros > kFullResidualMaximumNonzeros
        || input.spring_nonzeros > kFullResidualMaximumNonzeros
        || !checked_product(
            input.frame_element_count, kFullResidualFrameDofCount, frame_dof_count)
        || !checked_product(
            input.frame_element_count, kFullResidualFrameMatrixCount, frame_matrix_count)
        || input.frame_dofs.size() != frame_dof_count
        || input.frame_stiffness.size() != frame_matrix_count
        || input.external_force.size() != input.order
        || input.free_dofs.size() != input.free_dof_count) {
        throw std::invalid_argument("full residual operator dimensions are outside the bounded domain");
    }
    require_finite(input.frame_stiffness, "frame stiffness");
    require_finite(input.external_force, "external force");
    for (const auto dof : input.frame_dofs) {
        if (dof >= input.order) {
            throw std::invalid_argument("frame degree of freedom is out of range");
        }
    }
    std::vector<bool> free_seen(input.order, false);
    for (const auto dof : input.free_dofs) {
        if (dof >= input.order || free_seen[static_cast<std::size_t>(dof)]) {
            throw std::invalid_argument("free degree of freedom is out of range or duplicated");
        }
        free_seen[static_cast<std::size_t>(dof)] = true;
    }
    validate_csr(
        input.shell_row_offsets,
        input.shell_column_indices,
        input.shell_values,
        input.order,
        input.shell_nonzeros,
        "shell");
    validate_csr(
        input.spring_row_offsets,
        input.spring_column_indices,
        input.spring_values,
        input.order,
        input.spring_nonzeros,
        "spring");
    return {
        input.frame_element_count,
        input.order,
        input.shell_nonzeros,
        input.spring_nonzeros,
        input.free_dof_count,
        {input.frame_dofs.begin(), input.frame_dofs.end()},
        {input.frame_stiffness.begin(), input.frame_stiffness.end()},
        {input.shell_row_offsets.begin(), input.shell_row_offsets.end()},
        {input.shell_column_indices.begin(), input.shell_column_indices.end()},
        {input.shell_values.begin(), input.shell_values.end()},
        {input.spring_row_offsets.begin(), input.spring_row_offsets.end()},
        {input.spring_column_indices.begin(), input.spring_column_indices.end()},
        {input.spring_values.begin(), input.spring_values.end()},
        {input.external_force.begin(), input.external_force.end()},
        {input.free_dofs.begin(), input.free_dofs.end()},
    };
}

std::unique_ptr<FullResidualContext> make_cpu_full_residual_context(
    FullResidualOperator operator_data) {
    return std::make_unique<CpuFullResidualContext>(std::move(operator_data));
}

void validate_full_residual_evaluation(
    const FullResidualOperator& operator_data,
    const std::span<const double> states,
    const std::size_t batch_size,
    const std::uint32_t repetitions,
    const std::size_t residual_length) {
    std::size_t state_count = 0U;
    std::size_t output_count = 0U;
    if (batch_size == 0U || batch_size > kFullResidualMaximumBatchSize || repetitions == 0U
        || repetitions > kFullResidualMaximumRepetitions
        || !checked_product(batch_size, operator_data.order, state_count)
        || !checked_product(batch_size, operator_data.free_dof_count, output_count)
        || state_count > kFullResidualMaximumValueCount
        || output_count > kFullResidualMaximumValueCount
        || states.size() != state_count || residual_length != output_count) {
        throw std::invalid_argument("full residual evaluation dimensions are invalid");
    }
    require_finite(states, "full residual state");
}

}  // namespace structural::solver_cpu
