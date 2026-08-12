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

[[nodiscard]] sa_buffer_view_v1 input(const std::span<const double> values) {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values.empty() ? nullptr : values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

[[nodiscard]] sa_mut_buffer_view_v1 output(const std::span<double> values) {
    return {
        SA_ABI_V1_9,
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

[[nodiscard]] sa_dense_symmetric_matrix_v1 matrix(
    const std::uint64_t order,
    const std::span<const double> values) {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_dense_symmetric_matrix_v1)),
        order,
        input(values),
        {0U, 0U},
    };
}

[[nodiscard]] sa_generalized_eigen_config_v1 config(
    const std::uint32_t mode_count,
    const bool buckling = false) {
    return {
        SA_ABI_V1_9,
        static_cast<std::uint32_t>(sizeof(sa_generalized_eigen_config_v1)),
        mode_count,
        128U,
        0U,
        0U,
        1.0e-12,
        1.0e-12,
        1.0e-12,
        1.0e-10,
        buckling ? 1.0e-9 : 1.0e-10,
        buckling ? 1.0e-8 : 1.0e-10,
        1.0e-14,
        {0U, 0U},
    };
}

struct ModalStorage {
    std::array<double, 2> eigenvalue {91.0, 92.0};
    std::array<double, 2> omega {93.0, 94.0};
    std::array<double, 2> frequency {95.0, 96.0};
    std::array<double, 2> period {97.0, 98.0};
    std::array<double, 6> shapes {101.0, 102.0, 103.0, 104.0, 105.0, 106.0};
    std::array<double, 2> generalized_mass {107.0, 108.0};
    std::array<double, 2> generalized_stiffness {109.0, 110.0};
    std::array<double, 2> residual {111.0, 112.0};

    [[nodiscard]] sa_modal_outputs_v1 descriptor() {
        return {
            SA_ABI_V1_9,
            static_cast<std::uint32_t>(sizeof(sa_modal_outputs_v1)),
            output(eigenvalue),
            output(omega),
            output(frequency),
            output(period),
            output(shapes),
            output(generalized_mass),
            output(generalized_stiffness),
            output(residual),
            {0U, 0U},
        };
    }
};

struct BucklingStorage {
    std::array<double, 2> load_factor {91.0, 92.0};
    std::array<double, 6> shapes {93.0, 94.0, 95.0, 96.0, 97.0, 98.0};
    std::array<double, 2> elastic {99.0, 100.0};
    std::array<double, 2> geometric {101.0, 102.0};
    std::array<double, 2> residual {103.0, 104.0};

    [[nodiscard]] sa_buckling_outputs_v1 descriptor() {
        return {
            SA_ABI_V1_9,
            static_cast<std::uint32_t>(sizeof(sa_buckling_outputs_v1)),
            output(load_factor),
            output(shapes),
            output(elastic),
            output(geometric),
            output(residual),
            {0U, 0U},
        };
    }
};

template <typename Result>
[[nodiscard]] Result result_sentinel() {
    Result result {};
    std::memset(&result, 0xA5, sizeof(result));
    result.abi_version = SA_ABI_V1_9;
    result.struct_size = static_cast<std::uint32_t>(sizeof(result));
    return result;
}

[[nodiscard]] bool near(
    const double left,
    const double right,
    const double tolerance = 5.0e-11) {
    return std::abs(left - right)
        <= tolerance * std::max({1.0, std::abs(left), std::abs(right)});
}

[[nodiscard]] bool table_is_append_only() {
    const auto old = load(SA_ABI_V1_8);
    CHECK(old.sparse_linear_solve != nullptr);
    CHECK(old.modal_solve == nullptr);
    CHECK(old.buckling_solve == nullptr);
    CHECK((old.capabilities & SA_CAPABILITY_GENERALIZED_EIGEN_CPU) == 0U);

    const auto current = load(SA_ABI_V1_9);
    CHECK(current.sparse_linear_solve != nullptr);
    CHECK(current.modal_solve != nullptr);
    CHECK(current.buckling_solve != nullptr);
    CHECK((current.capabilities & SA_CAPABILITY_GENERALIZED_EIGEN_CPU) != 0U);
    CHECK(current.struct_size == sizeof(sa_api_v1));
    CHECK(SA_API_V1_8_MIN_SIZE == offsetof(sa_api_v1, modal_solve));
    CHECK(SA_API_V1_9_MIN_SIZE == offsetof(sa_api_v1, sparse_linear_begin));
    return true;
}

[[nodiscard]] bool caller_owned_modal_and_buckling_results_are_exact() {
    const auto api = load(SA_ABI_V1_9);
    const std::array<double, 9> modal_stiffness {
        0.0, 0.0, 0.0,
        0.0, 4.0, 0.0,
        0.0, 0.0, 9.0,
    };
    const std::array<double, 9> identity {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    };
    const auto stiffness = matrix(3U, modal_stiffness);
    const auto mass = matrix(3U, identity);
    const std::span<const double> no_scale {};
    const auto scale = input(no_scale);
    const auto modal_config = config(2U);
    ModalStorage modal_storage;
    const auto modal_outputs = modal_storage.descriptor();
    auto modal_result = result_sentinel<sa_modal_result_v1>();
    CHECK(api.modal_solve(
              &modal_config,
              &stiffness,
              &mass,
              &scale,
              &modal_outputs,
              &modal_result,
              nullptr)
          == SA_OK);
    CHECK((modal_storage.eigenvalue == std::array<double, 2> {4.0, 9.0}));
    CHECK((modal_storage.omega == std::array<double, 2> {2.0, 3.0}));
    CHECK(near(modal_storage.frequency[0], 1.0 / std::acos(-1.0)));
    CHECK(near(modal_storage.period[0], std::acos(-1.0)));
    CHECK((modal_storage.shapes
           == std::array<double, 6> {0.0, 1.0, 0.0, 0.0, 0.0, 1.0}));
    CHECK((modal_storage.generalized_mass == std::array<double, 2> {1.0, 1.0}));
    CHECK((modal_storage.generalized_stiffness == std::array<double, 2> {4.0, 9.0}));
    CHECK(modal_result.solver_status == SA_SOLVER_CONVERGED);
    CHECK(modal_result.rigid_mode_count == 1U);
    CHECK(modal_result.output_mode_count == 2U);
    CHECK(modal_result.output_shape_length == 6U);
    CHECK(modal_result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(modal_result.fallback_count == 0U);
    CHECK(modal_result.reserved[0] == 0U && modal_result.reserved[1] == 0U);

    const std::array<double, 9> buckling_stiffness {
        6.0, 0.0, 0.0,
        0.0, 8.0, 0.0,
        0.0, 0.0, 10.0,
    };
    const std::array<double, 9> geometric {
        3.0, 0.0, 0.0,
        0.0, 2.0, 0.0,
        0.0, 0.0, 0.0,
    };
    const auto elastic_matrix = matrix(3U, buckling_stiffness);
    const auto geometric_matrix = matrix(3U, geometric);
    const auto buckling_config = config(2U, true);
    BucklingStorage buckling_storage;
    const auto buckling_outputs = buckling_storage.descriptor();
    auto buckling_result = result_sentinel<sa_buckling_result_v1>();
    CHECK(api.buckling_solve(
              &buckling_config,
              &elastic_matrix,
              &geometric_matrix,
              &scale,
              &buckling_outputs,
              &buckling_result,
              nullptr)
          == SA_OK);
    CHECK((buckling_storage.load_factor == std::array<double, 2> {2.0, 4.0}));
    CHECK(near(buckling_storage.shapes[0], 1.0 / std::sqrt(6.0)));
    CHECK(near(buckling_storage.shapes[4], 1.0 / std::sqrt(8.0)));
    CHECK(near(buckling_storage.elastic[0], 1.0));
    CHECK(near(buckling_storage.geometric[0], 0.5));
    CHECK(buckling_result.finite_positive_eigenvalue_count == 2U);
    CHECK(buckling_result.geometric_stiffness_positive_rank == 2U);
    CHECK(buckling_result.critical_load_factor == 2.0);
    CHECK(buckling_result.output_mode_count == 2U);
    CHECK(buckling_result.output_shape_length == 6U);
    CHECK(buckling_result.execution_backend == SA_EXECUTION_BACKEND_CPU);
    CHECK(buckling_result.fallback_count == 0U);
    return true;
}

[[nodiscard]] bool failures_are_atomic_and_taxonomized() {
    const auto api = load(SA_ABI_V1_9);
    std::array<double, 9> stiffness_values {
        4.0, 0.0, 0.0,
        0.0, 4.0, 0.0,
        0.0, 0.0, 9.0,
    };
    const std::array<double, 9> identity {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    };
    auto stiffness = matrix(3U, stiffness_values);
    const auto mass = matrix(3U, identity);
    const std::span<const double> no_scale {};
    const auto scale = input(no_scale);
    auto modal_config = config(1U);
    ModalStorage storage;
    const auto untouched_storage = storage;
    auto outputs = storage.descriptor();
    const auto untouched_result = result_sentinel<sa_modal_result_v1>();
    auto result = untouched_result;

    CHECK(api.modal_solve(
              &modal_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&storage, &untouched_storage, sizeof(storage)) == 0);
    CHECK(std::memcmp(&result, &untouched_result, sizeof(result)) == 0);

    stiffness_values[1] = 0.25;
    stiffness = matrix(3U, stiffness_values);
    modal_config.mode_count = 2U;
    CHECK(api.modal_solve(
              &modal_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    CHECK(std::memcmp(&storage, &untouched_storage, sizeof(storage)) == 0);

    stiffness_values = {
        4.0, 0.3, 0.2,
        0.3, 5.0, 0.4,
        0.2, 0.4, 7.0,
    };
    stiffness = matrix(3U, stiffness_values);
    modal_config.maximum_sweeps = 1U;
    CHECK(api.modal_solve(
              &modal_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_NONCONVERGENCE);
    CHECK(std::memcmp(&storage, &untouched_storage, sizeof(storage)) == 0);
    CHECK(std::memcmp(&result, &untouched_result, sizeof(result)) == 0);
    return true;
}

[[nodiscard]] bool metadata_and_overlap_fail_closed_while_inputs_may_alias() {
    const auto api = load(SA_ABI_V1_9);
    const std::array<double, 4> aliased_positive {
        4.0, 0.0,
        0.0, 9.0,
    };
    const auto aliased_stiffness = matrix(2U, aliased_positive);
    const auto aliased_mass = matrix(2U, aliased_positive);
    const std::span<const double> no_scale {};
    const auto scale = input(no_scale);
    const auto aliased_config = config(2U);
    ModalStorage aliased_storage;
    const auto aliased_outputs = aliased_storage.descriptor();
    auto result = result_sentinel<sa_modal_result_v1>();
    CHECK(api.modal_solve(
              &aliased_config,
              &aliased_stiffness,
              &aliased_mass,
              &scale,
              &aliased_outputs,
              &result,
              nullptr)
          == SA_OK);
    CHECK((aliased_storage.eigenvalue == std::array<double, 2> {1.0, 1.0}));
    CHECK(result.output_shape_length == 4U);

    const std::array<double, 9> positive {
        4.0, 0.0, 0.0,
        0.0, 5.0, 0.0,
        0.0, 0.0, 9.0,
    };
    const auto stiffness = matrix(3U, positive);
    const std::array<double, 9> identity {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    };
    const auto mass = matrix(3U, identity);
    const auto valid_config = config(2U);
    ModalStorage storage;
    auto outputs = storage.descriptor();

    storage = {};
    outputs = storage.descriptor();
    outputs.omega_rad_per_s.data = outputs.eigenvalue_rad2_per_s2.data;
    CHECK(api.modal_solve(
              &valid_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    outputs = storage.descriptor();
    outputs.frequency_hz.data = const_cast<void*>(stiffness.values.data);
    CHECK(api.modal_solve(
              &valid_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);

    outputs = storage.descriptor();
    outputs.period_s.length = 1U;
    CHECK(api.modal_solve(
              &valid_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_BUFFER_TOO_SMALL);

    outputs = storage.descriptor();
    outputs.residual_relative_inf.stride_bytes = 16U;
    CHECK(api.modal_solve(
              &valid_config, &stiffness, &mass, &scale, &outputs, &result, nullptr)
          == SA_ERR_INVALID_ARGUMENT);
    return true;
}

[[nodiscard]] bool immutable_operations_are_reentrant_and_bitwise_repeatable() {
    const auto api = load(SA_ABI_V1_9);
    const std::array<double, 9> stiffness_values {
        6.0, -1.0, 0.0,
        -1.0, 8.0, -0.5,
        0.0, -0.5, 10.0,
    };
    const std::array<double, 9> mass_values {
        2.0, 0.0, 0.0,
        0.0, 3.0, 0.0,
        0.0, 0.0, 4.0,
    };
    const auto stiffness = matrix(3U, stiffness_values);
    const auto mass = matrix(3U, mass_values);
    const std::span<const double> no_scale {};
    const auto scale = input(no_scale);
    const auto valid_config = config(2U);
    std::atomic<bool> passed {true};
    ModalStorage baseline_storage;
    const auto baseline_outputs = baseline_storage.descriptor();
    auto baseline_result = result_sentinel<sa_modal_result_v1>();
    CHECK(api.modal_solve(
              &valid_config,
              &stiffness,
              &mass,
              &scale,
              &baseline_outputs,
              &baseline_result,
              nullptr)
          == SA_OK);
    const auto baseline = baseline_storage.eigenvalue;
    std::vector<std::thread> workers;
    for (std::size_t worker_index = 0U; worker_index < 10U; ++worker_index) {
        static_cast<void>(worker_index);
        workers.emplace_back([&] {
            ModalStorage storage;
            const auto outputs = storage.descriptor();
            auto result = result_sentinel<sa_modal_result_v1>();
            if (api.modal_solve(
                    &valid_config,
                    &stiffness,
                    &mass,
                    &scale,
                    &outputs,
                    &result,
                    nullptr)
                    != SA_OK
                || result.fallback_count != 0U) {
                passed.store(false, std::memory_order_relaxed);
                return;
            }
            if (std::memcmp(
                    baseline.data(), storage.eigenvalue.data(), sizeof(baseline))
                != 0) {
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
        caller_owned_modal_and_buckling_results_are_exact,
        failures_are_atomic_and_taxonomized,
        metadata_and_overlap_fail_closed_while_inputs_may_alias,
        immutable_operations_are_reentrant_and_bitwise_repeatable,
    };
    for (const auto test : tests) {
        if (!test()) {
            return EXIT_FAILURE;
        }
    }
    return EXIT_SUCCESS;
}
