#include "generalized_eigen.hpp"

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
    std::vector<double> stiffness(order * order, 0.0);
    std::vector<double> metric(order * order, 0.0);
    for (std::size_t row = 0U; row < order; ++row) {
        double stiffness_diagonal = 1.0;
        double metric_diagonal = 1.0;
        for (std::size_t column = row + 1U; column < order; ++column) {
            const auto offset = 1U + row * order + column;
            const double value =
                (static_cast<double>(data[offset % size]) - 127.5) / 2048.0;
            const double metric_value =
                (static_cast<double>(data[(offset + 7U) % size]) - 127.5) / 4096.0;
            stiffness[row * order + column] = value;
            stiffness[column * order + row] = value;
            metric[row * order + column] = metric_value;
            metric[column * order + row] = metric_value;
            stiffness_diagonal += std::abs(value);
            metric_diagonal += std::abs(metric_value);
            stiffness[column * order + column] += std::abs(value);
            metric[column * order + column] += std::abs(metric_value);
        }
        stiffness[row * order + row] += stiffness_diagonal;
        metric[row * order + row] += metric_diagonal;
    }
    const auto mutation = size > 1U ? data[1] % 6U : 0U;
    if (mutation == 1U && order > 1U) {
        stiffness[1U] += 1.0;
    } else if (mutation == 2U) {
        metric[0U] = 0.0;
    } else if (mutation == 3U) {
        stiffness[0U] = std::numeric_limits<double>::quiet_NaN();
    } else if (mutation == 4U) {
        metric[0U] = -metric[0U];
    } else if (mutation == 5U && order > 1U) {
        metric.pop_back();
    }

    try {
        auto config = structural::solver_cpu::default_modal_eigen_config(1U);
        config.maximum_sweeps = 32U;
        static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
            {order, stiffness}, {order, metric}, {}, config));
        static_cast<void>(structural::solver_cpu::solve_dense_linear_buckling(
            {order, stiffness}, {order, metric}, {},
            structural::solver_cpu::default_buckling_eigen_config(1U)));
    } catch (const std::invalid_argument&) {
    }
    return 0;
}
