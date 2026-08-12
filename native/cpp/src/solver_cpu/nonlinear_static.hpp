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

/// Run the deterministic serial FP64 story-frame Newton reference kernel.
[[nodiscard]] NonlinearStaticResult solve_nonlinear_static(
    const NonlinearStaticConfig& config,
    const NonlinearStaticInputs& inputs);

} // namespace structural::solver_cpu

#endif
