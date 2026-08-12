#include "track_point_load.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <iostream>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

[[nodiscard]] bool near(const double actual, const double expected) {
    return std::abs(actual - expected) <= 1.0e-15;
}

[[nodiscard]] structural::solver_cpu::TrackPointLoadConfig config() {
    return {
        10.0,
        9U,
        structural::solver_cpu::TrackSupportType::pinned,
        structural::solver_cpu::TrackTheory::euler,
        1.0e8,
        1.0e9,
        1.0e5,
        1.0e4,
        1.0e-9,
        500U,
        -10'000.0,
        5.0,
    };
}

[[nodiscard]] bool euler_case_matches_the_frozen_rust_oracle() {
    const auto result = structural::solver_cpu::solve_track_point_load(config());
    constexpr std::array expected_displacement {
        0.0,
        -0.0007037926926320691,
        -0.001321670876610801,
        -0.00176598837526238,
        -0.001945845157517316,
        -0.0017659883752623807,
        -0.0013216708766108014,
        -0.0007037926926320691,
        0.0,
    };
    constexpr std::array expected_rotation {
        -0.0005286683506443204,
        -0.0005286683506443204,
        -0.0004248782730521244,
        -0.00024966971236260597,
        -2.6020852139652105e-19,
        0.0002496697123626058,
        0.00042487827305212465,
        0.0005286683506443206,
        0.0005286683506443206,
    };

    CHECK(result.converged);
    CHECK(result.iterations == 4U);
    CHECK(near(result.residual_inf, 7.657748132248844e-10));
    CHECK(near(result.max_abs_displacement_m, 0.001945845157517316));
    CHECK(near(result.mid_displacement_m, -0.001945845157517316));
    CHECK(result.displacement_m.size() == expected_displacement.size());
    CHECK(result.rotation_rad.size() == expected_rotation.size());
    for (std::size_t index = 0U; index < expected_displacement.size(); ++index) {
        CHECK(near(result.displacement_m[index], expected_displacement[index]));
        CHECK(near(result.rotation_rad[index], expected_rotation[index]));
    }
    return true;
}

[[nodiscard]] bool reduced_timoshenko_mode_is_deterministic_and_more_flexible() {
    const auto euler = structural::solver_cpu::solve_track_point_load(config());
    auto timoshenko_config = config();
    timoshenko_config.theory = structural::solver_cpu::TrackTheory::timoshenko_reduced;
    const auto first = structural::solver_cpu::solve_track_point_load(timoshenko_config);
    const auto second = structural::solver_cpu::solve_track_point_load(timoshenko_config);

    CHECK(first.converged);
    CHECK(first.iterations == euler.iterations);
    CHECK(first.displacement_m == second.displacement_m);
    CHECK(first.rotation_rad == second.rotation_rad);
    CHECK(std::abs(first.mid_displacement_m) > std::abs(euler.mid_displacement_m));
    return true;
}

} // namespace

int main() {
    const std::array tests {
        euler_case_matches_the_frozen_rust_oracle,
        reduced_timoshenko_mode_is_deterministic_and_more_flexible,
    };
    for (const auto test : tests) {
        if (!test()) {
            return 1;
        }
    }
    return 0;
}
