#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <span>
#include <thread>
#include <vector>

namespace {

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            std::cerr << "check failed at line " << __LINE__ << ": " #condition << '\n';          \
            return false;                                                                           \
        }                                                                                           \
    } while (false)

struct ErrorStorage {
    std::array<char, 160> bytes {};
    sa_error_buffer_v1 descriptor;

    explicit ErrorStorage(const std::uint32_t version = SA_ABI_V1_8)
        : descriptor {
            version,
            static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
            bytes.data(),
            bytes.size(),
            0U,
        } {}
};

template <typename Value>
[[nodiscard]] sa_buffer_view_v1 input(
    const std::span<const Value> values,
    const std::uint32_t element_type,
    const std::uint32_t version = SA_ABI_V1_8) {
    return {
        version,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values.empty() ? nullptr : values.data(),
        values.size(),
        sizeof(Value),
        element_type,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_mut_buffer_view_v1 output(
    const std::span<double> values,
    const std::uint32_t version = SA_ABI_V1_8) {
    return {
        version,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

struct Case {
    std::array<std::uint64_t, 6> rows {0U, 2U, 5U, 8U, 11U, 13U};
    std::array<std::uint32_t, 13> columns {
        0U, 1U, 0U, 1U, 2U, 1U, 2U, 3U, 2U, 3U, 4U, 3U, 4U};
    std::array<double, 13> values {
        4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0,
        -1.0, -1.0, 3.0, -1.0, -1.0, 2.0};
    std::array<double, 5> rhs {6.0, -12.0, 18.0, -20.0, 14.0};

    [[nodiscard]] sa_sparse_csr_matrix_v1 matrix(
        const std::uint32_t version = SA_ABI_V1_8) const {
        return {
            version,
            static_cast<std::uint32_t>(sizeof(sa_sparse_csr_matrix_v1)),
            5U,
            input<std::uint64_t>(rows, SA_ELEMENT_TYPE_U64, version),
            input<std::uint32_t>(columns, SA_ELEMENT_TYPE_U32, version),
            input<double>(values, SA_ELEMENT_TYPE_F64, version),
            {0U, 0U},
        };
    }
};

[[nodiscard]] sa_sparse_linear_config_v1 config(
    const std::uint32_t version = SA_ABI_V1_8) {
    return {
        version,
        static_cast<std::uint32_t>(sizeof(sa_sparse_linear_config_v1)),
        100U,
        0U,
        1.0e-13,
        1.0e-13,
        0.0,
        {0U, 0U},
    };
}

[[nodiscard]] sa_sparse_linear_result_v1 result_sentinel() {
    sa_sparse_linear_result_v1 result {};
    std::memset(&result, 0xA5, sizeof(result));
    result.abi_version = SA_ABI_V1_8;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    return result;
}

[[nodiscard]] sa_api_v1 load(const std::uint32_t version) {
    const sa_api_request_v1 request {
        version,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = version;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    if (sa_get_api_v1(&request, &api, nullptr) != SA_OK) {
        std::abort();
    }
    return api;
}

[[nodiscard]] bool table_is_append_only() {
    const auto old = load(SA_ABI_V1_7);
    CHECK(old.reference_element_evaluate != nullptr);
    CHECK(old.sparse_linear_solve == nullptr);
    CHECK((old.capabilities & SA_CAPABILITY_SPARSE_LINEAR_CPU) == 0U);
    const auto current = load(SA_ABI_V1_8);
    CHECK(current.reference_element_evaluate != nullptr);
    CHECK(current.sparse_linear_solve != nullptr);
    CHECK((current.capabilities & SA_CAPABILITY_SPARSE_LINEAR_CPU) != 0U);
    CHECK(current.struct_size == sizeof(sa_api_v1));
    CHECK(SA_API_V1_7_MIN_SIZE == offsetof(sa_api_v1, sparse_linear_solve));
    CHECK(SA_API_V1_8_MIN_SIZE == offsetof(sa_api_v1, modal_solve));
    const auto spectral = load(SA_ABI_V1_9);
    CHECK(spectral.modal_solve != nullptr && spectral.buckling_solve != nullptr);
    CHECK(spectral.sparse_linear_begin == nullptr);
    CHECK(spectral.sparse_linear_advance == nullptr);
    CHECK((spectral.capabilities & SA_CAPABILITY_SPARSE_LINEAR_RESTART_CPU) == 0U);
    const auto restart = load(SA_ABI_V1_10);
    CHECK(restart.sparse_linear_begin != nullptr);
    CHECK(restart.sparse_linear_advance != nullptr);
    CHECK((restart.capabilities & SA_CAPABILITY_SPARSE_LINEAR_RESTART_CPU) != 0U);
    CHECK(SA_API_V1_9_MIN_SIZE == offsetof(sa_api_v1, sparse_linear_begin));
    CHECK(SA_API_V1_10_MIN_SIZE == offsetof(sa_api_v1, nonlinear_static_begin));
    return true;
}

struct RestartBuffers {
    std::array<double, 5> solution {};
    std::array<double, 5> residual {};
    std::array<double, 5> direction {};
    std::array<double, 5> diagonal_inverse {};
};

[[nodiscard]] sa_sparse_linear_state_v1 restart_state(RestartBuffers& buffers) {
    return {
        SA_ABI_V1_10,
        static_cast<std::uint32_t>(sizeof(sa_sparse_linear_state_v1)),
        SA_SPARSE_LINEAR_EXECUTION_ACTIVE,
        SA_SOLVER_NONCONVERGENCE,
        0U,
        SA_EXECUTION_BACKEND_CPU,
        0U,
        0U,
        0.0,
        0.0,
        0.0,
        0.0,
        5U,
        output(buffers.solution, SA_ABI_V1_10),
        output(buffers.residual, SA_ABI_V1_10),
        output(buffers.direction, SA_ABI_V1_10),
        output(buffers.diagonal_inverse, SA_ABI_V1_10),
        {0U, 0U},
    };
}

[[nodiscard]] bool same_restart_state(
    const sa_sparse_linear_state_v1& left,
    const RestartBuffers& left_buffers,
    const sa_sparse_linear_state_v1& right,
    const RestartBuffers& right_buffers) {
    return left.abi_version == right.abi_version && left.struct_size == right.struct_size
        && left.execution_status == right.execution_status
        && left.solver_status == right.solver_status && left.iterations == right.iterations
        && left.execution_backend == right.execution_backend
        && left.fallback_count == right.fallback_count
        && left.reserved_u32 == right.reserved_u32
        && left.initial_residual_inf == right.initial_residual_inf
        && left.convergence_limit == right.convergence_limit && left.rho == right.rho
        && left.last_increment_inf == right.last_increment_inf
        && left.vector_length == right.vector_length && left.reserved[0] == right.reserved[0]
        && left.reserved[1] == right.reserved[1]
        && left_buffers.solution == right_buffers.solution
        && left_buffers.residual == right_buffers.residual
        && left_buffers.direction == right_buffers.direction
        && left_buffers.diagonal_inverse == right_buffers.diagonal_inverse;
}

[[nodiscard]] bool caller_owned_restart_is_complete_and_failure_atomic() {
    const auto api = load(SA_ABI_V1_10);
    Case data;
    auto matrix = data.matrix(SA_ABI_V1_10);
    const auto rhs = input<double>(data.rhs, SA_ELEMENT_TYPE_F64, SA_ABI_V1_10);
    const std::span<const double> no_initial {};
    const auto initial = input<double>(
        no_initial, SA_ELEMENT_TYPE_F64, SA_ABI_V1_10);
    const auto valid_config = config(SA_ABI_V1_10);
    ErrorStorage error {SA_ABI_V1_10};

    RestartBuffers direct_buffers;
    auto direct = restart_state(direct_buffers);
    RestartBuffers segmented_buffers;
    auto segmented = restart_state(segmented_buffers);
    CHECK(api.sparse_linear_begin(
              &valid_config, &matrix, &rhs, &initial, &direct, &error.descriptor)
          == SA_OK);
    CHECK(api.sparse_linear_begin(
              &valid_config, &matrix, &rhs, &initial, &segmented, nullptr)
          == SA_OK);
    CHECK(same_restart_state(direct, direct_buffers, segmented, segmented_buffers));

    const auto zero_budget_state = segmented;
    const auto zero_budget_buffers = segmented_buffers;
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, 0U, &segmented, nullptr)
          == SA_OK);
    CHECK(same_restart_state(
        segmented, segmented_buffers, zero_budget_state, zero_budget_buffers));
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, 1U, &segmented, nullptr)
          == SA_OK);
    CHECK(segmented.execution_status == SA_SPARSE_LINEAR_EXECUTION_ACTIVE);
    CHECK(segmented.solver_status == SA_SOLVER_NONCONVERGENCE);
    CHECK(segmented.iterations == 1U);
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, 1U, &segmented, nullptr)
          == SA_OK);
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, UINT32_MAX, &segmented, nullptr)
          == SA_OK);
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, UINT32_MAX, &direct, nullptr)
          == SA_OK);
    CHECK(same_restart_state(direct, direct_buffers, segmented, segmented_buffers));
    CHECK(direct.execution_status == SA_SPARSE_LINEAR_EXECUTION_TERMINAL);
    CHECK(direct.solver_status == SA_SOLVER_CONVERGED);

    const auto terminal_state = direct;
    const auto terminal_buffers = direct_buffers;
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, 1U, &direct, nullptr)
          == SA_OK);
    CHECK(same_restart_state(direct, direct_buffers, terminal_state, terminal_buffers));

    RestartBuffers corrupt_buffers;
    auto corrupt = restart_state(corrupt_buffers);
    CHECK(api.sparse_linear_begin(
              &valid_config, &matrix, &rhs, &initial, &corrupt, nullptr)
          == SA_OK);
    corrupt.rho = std::numeric_limits<double>::quiet_NaN();
    const auto corrupt_buffers_before = corrupt_buffers;
    CHECK(api.sparse_linear_advance(
              &valid_config, &matrix, &rhs, 1U, &corrupt, &error.descriptor)
          == SA_ERR_CHECKPOINT_MISMATCH);
    CHECK(std::isnan(corrupt.rho));
    CHECK(corrupt_buffers.solution == corrupt_buffers_before.solution);
    CHECK(corrupt_buffers.residual == corrupt_buffers_before.residual);
    CHECK(corrupt_buffers.direction == corrupt_buffers_before.direction);
    CHECK(corrupt_buffers.diagonal_inverse == corrupt_buffers_before.diagonal_inverse);

    auto overlap = restart_state(corrupt_buffers);
    overlap.residual.data = overlap.solution.data;
    CHECK(api.sparse_linear_begin(
              &valid_config, &matrix, &rhs, &initial, &overlap, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    data.values[0] = 0.0;
    matrix = data.matrix(SA_ABI_V1_10);
    RestartBuffers singular_buffers;
    auto singular = restart_state(singular_buffers);
    CHECK(api.sparse_linear_begin(
              &valid_config, &matrix, &rhs, &initial, &singular, nullptr)
          == SA_OK);
    CHECK(singular.execution_status == SA_SPARSE_LINEAR_EXECUTION_TERMINAL);
    CHECK(singular.solver_status == SA_SOLVER_SINGULARITY);
    CHECK(singular.iterations == 0U);
    return true;
}

[[nodiscard]] bool caller_owned_spd_solve_matches_reference() {
    const auto api = load(SA_ABI_V1_8);
    const Case data;
    const auto matrix = data.matrix();
    const auto rhs = input<double>(data.rhs, SA_ELEMENT_TYPE_F64);
    const std::span<const double> no_initial {};
    const auto initial = input<double>(no_initial, SA_ELEMENT_TYPE_F64);
    const auto valid_config = config();
    std::array<double, 5> solution_values {};
    const auto solution = output(solution_values);
    auto result = result_sentinel();
    ErrorStorage error;
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, &error.descriptor)
          == SA_OK);
    const std::array<double, 5> expected {1.0, -2.0, 3.0, -4.0, 5.0};
    for (std::size_t index = 0U; index < expected.size(); ++index) {
        CHECK(std::abs(solution_values[index] - expected[index]) <= 2.0e-12);
    }
    CHECK(result.abi_version == SA_ABI_V1_8);
    CHECK(result.struct_size == sizeof(result));
    CHECK(result.solver_status == SA_SOLVER_CONVERGED);
    CHECK(result.iterations > 0U && result.iterations <= 5U);
    CHECK(result.final_residual_inf <= 1.0e-11);
    CHECK(result.output_length == 5U);
    CHECK(result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(result.fallback_count == 0U);
    CHECK(result.reserved[0] == 0U && result.reserved[1] == 0U);
    return true;
}

[[nodiscard]] bool failures_do_not_publish_partial_outputs() {
    const auto api = load(SA_ABI_V1_8);
    Case data;
    auto matrix = data.matrix();
    auto rhs = input<double>(data.rhs, SA_ELEMENT_TYPE_F64);
    const std::span<const double> no_initial {};
    auto initial = input<double>(no_initial, SA_ELEMENT_TYPE_F64);
    const auto valid_config = config();
    std::array<double, 5> solution_values {91.0, 92.0, 93.0, 94.0, 95.0};
    const auto untouched_solution = solution_values;
    auto solution = output(solution_values);
    const auto untouched_result = result_sentinel();
    auto result = untouched_result;

    data.rows.back() = 99U;
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(solution_values == untouched_solution);
    CHECK(std::memcmp(&result, &untouched_result, sizeof(result)) == 0);

    data.rows.back() = data.values.size();
    data.values[0] = 0.0;
    matrix = data.matrix();
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_SINGULARITY);
    CHECK(solution_values == untouched_solution);
    CHECK(std::memcmp(&result, &untouched_result, sizeof(result)) == 0);

    data.values[0] = -4.0;
    matrix = data.matrix();
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INDEFINITE_OPERATOR);
    CHECK(solution_values == untouched_solution);

    data.values[0] = 4.0;
    matrix = data.matrix();
    auto one_iteration = config();
    one_iteration.max_iterations = 1U;
    CHECK(api.sparse_linear_solve(
              &one_iteration, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(solution_values == untouched_solution);

    auto increment_limit = config();
    increment_limit.maximum_increment = 1.0e-20;
    CHECK(api.sparse_linear_solve(
              &increment_limit, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INCREMENT_LIMIT);
    CHECK(solution_values == untouched_solution);
    CHECK(std::memcmp(&result, &untouched_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool metadata_overlap_and_nonfinite_inputs_fail_closed() {
    const auto api = load(SA_ABI_V1_8);
    Case data;
    auto matrix = data.matrix();
    auto rhs = input<double>(data.rhs, SA_ELEMENT_TYPE_F64);
    const std::span<const double> no_initial {};
    const auto initial = input<double>(no_initial, SA_ELEMENT_TYPE_F64);
    const auto valid_config = config();
    std::array<double, 5> solution_values {1.0, 1.0, 1.0, 1.0, 1.0};
    auto solution = output(solution_values);
    auto result = result_sentinel();

    solution.data = data.rhs.data();
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    solution = output(solution_values);

    matrix.column_indices.stride_bytes = sizeof(std::uint32_t) * 2U;
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    matrix = data.matrix();

    data.values[0] = std::numeric_limits<double>::quiet_NaN();
    matrix = data.matrix();
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    data.values[0] = 4.0;
    matrix = data.matrix();
    solution.length = 4U;
    CHECK(api.sparse_linear_solve(
              &valid_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);
    return true;
}

[[nodiscard]] bool immutable_inputs_are_reentrant() {
    const auto api = load(SA_ABI_V1_8);
    const Case data;
    const auto matrix = data.matrix();
    const auto rhs = input<double>(data.rhs, SA_ELEMENT_TYPE_F64);
    const std::span<const double> no_initial {};
    const auto initial = input<double>(no_initial, SA_ELEMENT_TYPE_F64);
    std::atomic<bool> passed {true};
    std::vector<std::thread> workers;
    for (std::size_t worker = 0U; worker < 12U; ++worker) {
        workers.emplace_back([api, &matrix, &rhs, &initial, &passed] {
            std::array<double, 5> values {};
            const auto solution = output(values);
            auto result = result_sentinel();
            auto local_config = config();
            if (api.sparse_linear_solve(
                    &local_config, &matrix, &rhs, &initial, &solution, &result, nullptr)
                    != SA_OK
                || result.fallback_count != 0U || std::abs(values[4] - 5.0) > 2.0e-12) {
                passed.store(false, std::memory_order_relaxed);
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    CHECK(passed.load(std::memory_order_relaxed));
    return true;
}

}  // namespace

int main() {
    const std::array tests {
        table_is_append_only,
        caller_owned_restart_is_complete_and_failure_atomic,
        caller_owned_spd_solve_matches_reference,
        failures_do_not_publish_partial_outputs,
        metadata_overlap_and_nonfinite_inputs_fail_closed,
        immutable_inputs_are_reentrant,
    };
    for (const auto test : tests) {
        if (!test()) {
            return EXIT_FAILURE;
        }
    }
    return EXIT_SUCCESS;
}
