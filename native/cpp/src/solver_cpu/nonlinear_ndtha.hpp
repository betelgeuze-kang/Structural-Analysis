#ifndef STRUCTURAL_SOLVER_CPU_NONLINEAR_NDTHA_HPP
#define STRUCTURAL_SOLVER_CPU_NONLINEAR_NDTHA_HPP

#include <cstdint>
#include <span>
#include <vector>

namespace structural::solver_cpu {

struct NonlinearNdthaConfig {
    std::uint32_t story_count;
    std::uint32_t step_count;
    double dt_s;
    double newmark_beta;
    double newmark_gamma;
    double tolerance;
    std::uint32_t max_step_iterations;
    double adaptive_load_decay;
    double damping_force_cap_ratio;
    std::uint32_t newton_max_iter;
    double line_search_decay;
    double line_search_min;
    double hardening_ratio;
    double pdelta_factor;
    double collapse_drift_threshold_pct;
};

struct NonlinearNdthaInputs {
    std::span<const double> story_stiffness_n_per_m;
    std::span<const double> story_height_m;
    std::span<const double> story_axial_n;
    std::span<const double> story_yield_drift_m;
    std::span<const double> story_mass_kg;
    std::span<const double> story_damping_n_s_per_m;
    std::span<const double> floor_load_base_n;
    std::span<const double> acceleration_g;
};

struct NonlinearNdthaResponse {
    std::vector<double> top_displacement_m;
    std::vector<double> drift_ratio_pct;
    std::vector<double> base_shear_kn;
    std::vector<double> core_drift_pct;
    std::vector<double> core_shear_kn;
    std::vector<std::uint8_t> step_converged;
    std::vector<std::uint32_t> step_iterations;
    std::vector<std::uint32_t> step_plastic_story_count;
    std::vector<double> step_residual_inf;
    std::vector<double> story_drift_envelope_pct;
    std::vector<double> final_story_drift_pct;
};

struct NonlinearNdthaResult {
    bool converged_all_steps;
    bool collapsed;
    std::int32_t collapse_step;
    double collapse_time_s;
    double collapse_drift_ratio_pct;
    double collapse_top_displacement_m;
    std::uint32_t step_count_completed;
    std::uint32_t max_plastic_story_count;
    double max_drift_ratio_pct;
    double avg_step_iterations;
    double residual_top_displacement_m;
    double residual_drift_ratio_pct;
    std::uint32_t total_line_search_backtracks;
    NonlinearNdthaResponse response;
};

enum class NonlinearNdthaExecutionStatus : std::uint32_t {
    active = 0U,
    completed = 1U,
    collapsed = 2U,
    nonconverged = 3U,
};

/// Complete caller-owned state at a deterministic inter-step restart boundary.
struct NonlinearNdthaExecutionState {
    std::uint32_t next_step;
    NonlinearNdthaExecutionStatus status;
    std::int32_t collapse_step;
    double collapse_time_s;
    double collapse_drift_ratio_pct;
    double collapse_top_displacement_m;
    std::uint32_t max_plastic_story_count;
    double max_drift_ratio_pct;
    std::uint64_t adaptive_iteration_sum;
    std::uint32_t total_line_search_backtracks;
    std::vector<double> displacement_m;
    std::vector<double> velocity_m_per_s;
    std::vector<double> acceleration_m_per_s2;
    NonlinearNdthaResponse response;
};

/// Allocate the deterministic zero initial state for one bounded NDTHA case.
[[nodiscard]] NonlinearNdthaExecutionState make_nonlinear_ndtha_initial_state(
    const NonlinearNdthaConfig& config);

/// Advance at most `step_budget` inter-step boundaries and retain all restart state.
///
/// The supplied state is validated before execution and remains unchanged when validation or
/// allocation throws. A numerical nonconvergence is a committed terminal state rather than an
/// exception so the ABI boundary can map it to its stable error taxonomy.
void advance_nonlinear_ndtha(
    const NonlinearNdthaConfig& config,
    const NonlinearNdthaInputs& inputs,
    std::uint32_t step_budget,
    NonlinearNdthaExecutionState& state);

/// Project a validated execution state into the existing complete result contract.
[[nodiscard]] NonlinearNdthaResult finalize_nonlinear_ndtha(
    const NonlinearNdthaConfig& config,
    NonlinearNdthaExecutionState state);

/// Run the deterministic serial FP64 Newmark/Newton story-frame reference kernel.
[[nodiscard]] NonlinearNdthaResult solve_nonlinear_ndtha(
    const NonlinearNdthaConfig& config,
    const NonlinearNdthaInputs& inputs);

} // namespace structural::solver_cpu

#endif
