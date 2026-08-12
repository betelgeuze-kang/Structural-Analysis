#ifndef STRUCTURAL_SOLVER_CPU_TRACK_POINT_LOAD_HPP
#define STRUCTURAL_SOLVER_CPU_TRACK_POINT_LOAD_HPP

#include <cstdint>
#include <vector>

namespace structural::solver_cpu {

enum class TrackSupportType : std::uint32_t {
    pinned = 0U,
    fixed = 1U,
};

enum class TrackTheory : std::uint32_t {
    euler = 0U,
    timoshenko_reduced = 1U,
};

struct TrackPointLoadConfig {
    double length_m;
    std::uint32_t node_count;
    TrackSupportType support_type;
    TrackTheory theory;
    double bending_stiffness_n_m2;
    double shear_stiffness_n;
    double winkler_k_n_per_m2;
    double pasternak_g_n;
    double tolerance;
    std::uint32_t cg_max_iter;
    double point_force_n;
    double point_position_m;
};

struct TrackPointLoadResult {
    bool converged;
    std::uint32_t iterations;
    double residual_inf;
    double max_abs_displacement_m;
    double mid_displacement_m;
    std::vector<double> displacement_m;
    std::vector<double> rotation_rad;
};

/// Run the deterministic serial FP64 reference kernel for one point-load track case.
[[nodiscard]] TrackPointLoadResult solve_track_point_load(const TrackPointLoadConfig& config);

} // namespace structural::solver_cpu

#endif
