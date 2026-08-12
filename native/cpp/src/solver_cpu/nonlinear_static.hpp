#ifndef STRUCTURAL_SOLVER_CPU_NONLINEAR_STATIC_HPP
#define STRUCTURAL_SOLVER_CPU_NONLINEAR_STATIC_HPP

#include <cstdint>
#include <span>
#include <vector>

namespace structural::solver_cpu {

struct NonlinearStaticConfig {
    std::uint32_t story_count;
    double tolerance;
    std::uint32_t max_iter;
    double hardening_ratio;
    double line_search_decay;
    double line_search_min;
    double pdelta_factor;
};

struct NonlinearStaticInputs {
    std::span<const double> story_stiffness_n_per_m;
    std::span<const double> story_height_m;
    std::span<const double> story_axial_n;
    std::span<const double> story_yield_drift_m;
    std::span<const double> floor_load_n;
};

struct NonlinearStaticResult {
    bool converged;
    std::uint32_t iterations;
    double residual_inf;
    double residual_l2;
    double max_abs_displacement_m;
    double top_displacement_m;
    double base_shear_kn;
    std::uint32_t plastic_story_count;
    std::uint32_t line_search_backtracks;
    std::vector<double> displacement_m;
};

enum class NonlinearStaticExecutionStatus : std::uint32_t {
    active = 0U,
    converged = 1U,
    nonconverged = 2U,
};

/// Complete deterministic state at a published Newton iteration boundary.
struct NonlinearStaticExecutionState {
    NonlinearStaticExecutionStatus status {NonlinearStaticExecutionStatus::active};
    std::uint32_t iterations {0U};
    std::uint32_t line_search_backtracks {0U};
    double residual_inf {0.0};
    double residual_l2 {0.0};
    double max_abs_displacement_m {0.0};
    double top_displacement_m {0.0};
    double base_shear_kn {0.0};
    std::uint32_t plastic_story_count {0U};
    std::vector<double> displacement_m;
};

/// Validate the shared CPU/accelerator nonlinear-static problem contract.
void validate_nonlinear_static_problem(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs);

/// Validate the problem and construct the exact zero-displacement Newton boundary.
[[nodiscard]] NonlinearStaticExecutionState begin_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs);

/// Advance a complete state by at most `iteration_budget` Newton loop iterations.
void advance_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs,
    std::uint32_t iteration_budget,
    NonlinearStaticExecutionState& state);

/// Project any validated terminal or active state into the stable result structure.
[[nodiscard]] NonlinearStaticResult nonlinear_static_result(
    const NonlinearStaticExecutionState& state);

/// Run the deterministic serial FP64 story-frame Newton reference kernel.
[[nodiscard]] NonlinearStaticResult solve_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs);

} // namespace structural::solver_cpu

#endif
