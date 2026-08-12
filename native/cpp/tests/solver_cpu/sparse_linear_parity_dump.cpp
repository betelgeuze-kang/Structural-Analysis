#include "sparse_linear.hpp"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {

struct OwnedCsr {
    std::size_t order;
    std::vector<std::uint64_t> rows;
    std::vector<std::uint32_t> columns;
    std::vector<double> values;

    [[nodiscard]] structural::solver_cpu::CsrMatrixView view() const {
        return {order, rows, columns, values};
    }
};

void dump(const std::string_view name, const std::span<const double> values) {
    std::cout << name;
    for (const double value : values) {
        std::cout << '|' << std::setprecision(17) << value;
    }
    std::cout << '\n';
}

void run_case(
    const std::string_view name,
    const OwnedCsr& matrix,
    const std::span<const double> right_hand_side) {
    const structural::solver_cpu::SparseLinearConfig config {200U, 1.0e-13, 1.0e-13, 0.0};
    const auto result = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config);
    const std::array metrics {
        static_cast<double>(result.status),
        static_cast<double>(result.iterations),
        result.initial_residual_inf,
        result.final_residual_inf,
        result.final_residual_l2,
        result.last_increment_inf,
        static_cast<double>(result.fallback_count),
    };
    dump(std::string(name) + ".solution", result.solution);
    dump(std::string(name) + ".metrics", metrics);
}

}  // namespace

int main() {
    const OwnedCsr five {
        5U,
        {0U, 2U, 5U, 8U, 11U, 13U},
        {0U, 1U, 0U, 1U, 2U, 1U, 2U, 3U, 2U, 3U, 4U, 3U, 4U},
        {4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0,
         -1.0, 3.0, -1.0, -1.0, 2.0},
    };
    const std::array<double, 5> five_rhs {6.0, -12.0, 18.0, -20.0, 14.0};
    run_case("spd5", five, five_rhs);

    const OwnedCsr irregular {
        6U,
        {0U, 3U, 7U, 10U, 13U, 17U, 20U},
        {
            0U, 1U, 4U,
            0U, 1U, 2U, 5U,
            1U, 2U, 3U,
            2U, 3U, 4U,
            0U, 3U, 4U, 5U,
            1U, 4U, 5U,
        },
        {
            10.0, 2.0, 1.0,
            2.0, 9.0, -1.0, 1.0,
            -1.0, 8.0, 2.0,
            2.0, 7.0, -1.0,
            1.0, -1.0, 6.0, 1.0,
            1.0, 1.0, 5.0,
        },
    };
    const std::array<double, 6> irregular_rhs {9.0, -10.5, 6.0, 17.5, -9.0, 10.5};
    run_case("irregular6", irregular, irregular_rhs);

    const OwnedCsr scaled {
        4U,
        {0U, 1U, 2U, 3U, 4U},
        {0U, 1U, 2U, 3U},
        {1.0e-6, 2.0e-2, 3.0e2, 4.0e6},
    };
    const std::array<double, 4> scaled_rhs {2.0e-6, -6.0e-2, 1.2e3, -2.0e7};
    run_case("scaled4", scaled, scaled_rhs);

    const std::array<double, 5> zero_rhs {};
    run_case("zero5", five, zero_rhs);
    return EXIT_SUCCESS;
}
