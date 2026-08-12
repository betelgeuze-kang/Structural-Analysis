#ifndef STRUCTURAL_SOLVER_CPU_FULL_RESIDUAL_HPP
#define STRUCTURAL_SOLVER_CPU_FULL_RESIDUAL_HPP

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string_view>
#include <vector>

namespace structural::solver_cpu {

constexpr std::size_t kFullResidualFrameDofCount = 12U;
constexpr std::size_t kFullResidualFrameMatrixCount = 144U;
constexpr std::size_t kFullResidualMaximumOrder = 1'000'000U;
constexpr std::size_t kFullResidualMaximumFrameCount = 1'000'000U;
constexpr std::size_t kFullResidualMaximumNonzeros = 100'000'000U;
constexpr std::size_t kFullResidualMaximumBatchSize = 1'000'000U;
constexpr std::size_t kFullResidualMaximumValueCount = 100'000'000U;
constexpr std::uint32_t kFullResidualMaximumRepetitions = 10'000U;

struct FullResidualOperatorInput {
    std::size_t frame_element_count;
    std::size_t order;
    std::size_t shell_nonzeros;
    std::size_t spring_nonzeros;
    std::size_t free_dof_count;
    std::span<const std::uint64_t> frame_dofs;
    std::span<const double> frame_stiffness;
    std::span<const std::uint64_t> shell_row_offsets;
    std::span<const std::uint64_t> shell_column_indices;
    std::span<const double> shell_values;
    std::span<const std::uint64_t> spring_row_offsets;
    std::span<const std::uint64_t> spring_column_indices;
    std::span<const double> spring_values;
    std::span<const double> external_force;
    std::span<const std::uint64_t> free_dofs;
};

struct FullResidualOperator {
    std::size_t frame_element_count;
    std::size_t order;
    std::size_t shell_nonzeros;
    std::size_t spring_nonzeros;
    std::size_t free_dof_count;
    std::vector<std::uint64_t> frame_dofs;
    std::vector<double> frame_stiffness;
    std::vector<std::uint64_t> shell_row_offsets;
    std::vector<std::uint64_t> shell_column_indices;
    std::vector<double> shell_values;
    std::vector<std::uint64_t> spring_row_offsets;
    std::vector<std::uint64_t> spring_column_indices;
    std::vector<double> spring_values;
    std::vector<double> external_force;
    std::vector<std::uint64_t> free_dofs;
};

struct FullResidualMetrics {
    bool evaluation_buffers_reused;
    bool operator_device_resident;
    std::uint64_t h2d_bytes;
    std::uint64_t d2h_bytes;
    std::uint64_t h2d_transfer_count;
    std::uint64_t d2h_transfer_count;
    std::uint64_t synchronization_count;
    std::uint64_t kernel_launch_count;
    std::uint64_t device_buffer_bytes;
    std::uint64_t vram_total_bytes;
    std::uint64_t vram_free_before_bytes;
    std::uint64_t vram_free_after_bytes;
    double kernel_elapsed_ms_total;
    double kernel_elapsed_ms_mean;
    double output_abs_sum;
    double output_max_abs;
};

/// Validate every dimension, index, CSR invariant and finite value, then deep-copy the operator.
/// Invalid caller data throws `std::invalid_argument`; allocation failures propagate unchanged.
[[nodiscard]] FullResidualOperator make_full_residual_operator(
    const FullResidualOperatorInput& input);

class FullResidualContext {
  public:
    FullResidualContext() = default;
    FullResidualContext(const FullResidualContext&) = delete;
    FullResidualContext& operator=(const FullResidualContext&) = delete;
    virtual ~FullResidualContext() = default;

    [[nodiscard]] virtual std::uint32_t execution_backend() const noexcept = 0;
    [[nodiscard]] virtual std::int32_t device_id() const noexcept = 0;
    [[nodiscard]] virtual std::string_view device_name() const noexcept = 0;
    [[nodiscard]] virtual const FullResidualOperator& operator_data() const noexcept = 0;
    [[nodiscard]] virtual FullResidualMetrics creation_metrics() const noexcept = 0;

    /// Mutates reusable execution buffers and therefore requires exclusive external access.
    [[nodiscard]] virtual FullResidualMetrics evaluate(
        std::span<const double> states,
        std::size_t batch_size,
        std::uint32_t repetitions,
        std::span<double> residual) = 0;
};

[[nodiscard]] std::unique_ptr<FullResidualContext> make_cpu_full_residual_context(
    FullResidualOperator operator_data);

/// Shared CPU/HIP evaluation-shape and finite-value validation.
void validate_full_residual_evaluation(
    const FullResidualOperator& operator_data,
    std::span<const double> states,
    std::size_t batch_size,
    std::uint32_t repetitions,
    std::size_t residual_length);

}  // namespace structural::solver_cpu

#endif
