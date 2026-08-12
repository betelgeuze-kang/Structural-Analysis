#include "sparse_linear.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* const data,
    const std::size_t size) {
    if (size == 0U) {
        return 0;
    }
    const auto order = static_cast<std::size_t>(1U + data[0] % 8U);
    std::vector<std::uint64_t> rows(order + 1U, 0U);
    std::vector<std::uint32_t> columns(order * order, 0U);
    std::vector<double> values(order * order, 0.0);
    for (std::size_t row = 0U; row < order; ++row) {
        rows[row] = row * order;
        for (std::size_t column = 0U; column < order; ++column) {
            columns[row * order + column] = static_cast<std::uint32_t>(column);
        }
    }
    rows.back() = values.size();
    for (std::size_t row = 0U; row < order; ++row) {
        double diagonal = 1.0;
        for (std::size_t column = row + 1U; column < order; ++column) {
            const auto byte = data[(1U + row * order + column) % size];
            const double value = (static_cast<double>(byte) - 127.5) / 1024.0;
            values[row * order + column] = value;
            values[column * order + row] = value;
            diagonal += std::abs(value);
            values[column * order + column] += std::abs(value);
        }
        values[row * order + row] += diagonal;
    }
    std::vector<double> right_hand_side(order, 0.0);
    for (std::size_t index = 0U; index < order; ++index) {
        right_hand_side[index] =
            (static_cast<double>(data[(1U + index) % size]) - 127.5) / 8.0;
    }

    const auto mutation = size > 1U ? data[1] % 5U : 0U;
    if (mutation == 1U) {
        rows.back() += 1U;
    } else if (mutation == 2U && order > 1U) {
        columns[1U] = 0U;
    } else if (mutation == 3U) {
        values[0] = std::numeric_limits<double>::quiet_NaN();
    } else if (mutation == 4U && order > 1U) {
        values[1U] += 1.0;
    }

    try {
        const structural::solver_cpu::CsrMatrixView matrix {
            order, rows, columns, values};
        const structural::solver_cpu::SparseLinearConfig config {
            32U, 1.0e-10, 1.0e-10, 0.0};
        static_cast<void>(structural::solver_cpu::solve_sparse_spd_pcg(
            matrix, right_hand_side, {}, config));
    } catch (const std::invalid_argument&) {
    }
    return 0;
}
