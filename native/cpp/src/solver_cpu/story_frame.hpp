#ifndef STRUCTURAL_SOLVER_CPU_STORY_FRAME_HPP
#define STRUCTURAL_SOLVER_CPU_STORY_FRAME_HPP

#include <cstdint>
#include <span>
#include <vector>

namespace structural::solver_cpu::detail {

inline constexpr double kStoryFrameEpsilon = 1.0e-12;

struct StoryFrameConstitutiveConfig {
    double hardening_ratio;
    double pdelta_factor;
};

struct StoryFrameInputs {
    std::span<const double> story_stiffness_n_per_m;
    std::span<const double> story_height_m;
    std::span<const double> story_axial_n;
    std::span<const double> story_yield_drift_m;
};

struct StoryFrameAssemblyResult {
    double base_shear_kn;
    std::uint32_t plastic_story_count;
};

[[nodiscard]] double norm_inf(std::span<const double> values) noexcept;

[[nodiscard]] double norm_l2(std::span<const double> values) noexcept;

[[nodiscard]] bool solve_tridiagonal(
    std::span<const double> lower,
    std::span<const double> diagonal,
    std::span<const double> upper,
    std::span<const double> right_hand_side,
    std::span<double> output);

/// Evaluate the shared bilinear story law and assemble its resisting force and tangent.
///
/// Static Newton, transient Newton, JVP and result-recovery paths must consume this source rather
/// than maintaining independent constitutive implementations.
[[nodiscard]] StoryFrameAssemblyResult assemble_story_frame(
    std::span<const double> displacement_m,
    const StoryFrameConstitutiveConfig& config,
    const StoryFrameInputs& inputs,
    std::span<double> internal_force_n,
    std::span<double> lower_n_per_m,
    std::span<double> diagonal_n_per_m,
    std::span<double> upper_n_per_m);

void recover_story_response(
    std::span<const double> displacement_m,
    std::span<const double> story_height_m,
    std::span<const double> story_stiffness_n_per_m,
    std::span<double> drift_ratio_pct,
    std::span<double> shear_kn);

} // namespace structural::solver_cpu::detail

#endif
