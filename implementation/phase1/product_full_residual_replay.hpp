#ifndef STRUCTURAL_PRODUCT_FULL_RESIDUAL_REPLAY_HPP
#define STRUCTURAL_PRODUCT_FULL_RESIDUAL_REPLAY_HPP

#include "structural/abi_v1.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

namespace structural::compatibility::replay {

struct ErrorBuffer {
    std::array<char, 1024> bytes {};
    sa_error_buffer_v1 view {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_error_buffer_v1)),
        bytes.data(),
        bytes.size(),
        0U,
    };

    void reset() noexcept {
        bytes.fill('\0');
        view.required = 0U;
    }
};

inline void require_ok(
    const sa_status_code_v1 status,
    const std::string_view operation,
    ErrorBuffer& error) {
    if (status == SA_OK) {
        return;
    }
    const std::string detail = error.bytes.data();
    throw std::runtime_error(
        std::string(operation) + " failed with status " + std::to_string(status)
        + (detail.empty() ? std::string {} : ": " + detail));
}

inline std::string json_escape(const std::string_view value) {
    std::string output;
    output.reserve(value.size());
    for (const char value_character : value) {
        switch (value_character) {
        case '\\':
            output += "\\\\";
            break;
        case '"':
            output += "\\\"";
            break;
        case '\n':
            output += "\\n";
            break;
        case '\r':
            output += "\\r";
            break;
        case '\t':
            output += "\\t";
            break;
        default:
            output += value_character;
            break;
        }
    }
    return output;
}

inline std::size_t checked_count(
    const std::uint64_t value,
    const std::string_view label) {
    if (value > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error(std::string(label) + " exceeds size_t");
    }
    return static_cast<std::size_t>(value);
}

inline std::size_t checked_product(
    const std::size_t left,
    const std::size_t right,
    const std::string_view label) {
    if (left != 0U && right > std::numeric_limits<std::size_t>::max() / left) {
        throw std::runtime_error(std::string(label) + " size overflows");
    }
    return left * right;
}

template <typename Value>
std::vector<Value> read_binary(
    const std::string& path,
    const std::size_t expected_count) {
    const auto expected_bytes = checked_product(expected_count, sizeof(Value), "input");
    std::error_code size_error;
    const auto actual_bytes = std::filesystem::file_size(path, size_error);
    if (size_error || actual_bytes != expected_bytes) {
        throw std::runtime_error("input size mismatch: " + path);
    }
    std::ifstream input_stream(path, std::ios::binary);
    if (!input_stream) {
        throw std::runtime_error("failed to open input: " + path);
    }
    std::vector<Value> values(expected_count);
    if (expected_bytes != 0U) {
        input_stream.read(
            reinterpret_cast<char*>(values.data()),
            static_cast<std::streamsize>(expected_bytes));
    }
    if (!input_stream) {
        throw std::runtime_error("failed to read input: " + path);
    }
    return values;
}

template <typename Value>
void write_binary(
    const std::string& path,
    const std::vector<Value>& values) {
    std::ofstream output_stream(path, std::ios::binary | std::ios::trunc);
    if (!output_stream) {
        throw std::runtime_error("failed to open output: " + path);
    }
    if (!values.empty()) {
        output_stream.write(
            reinterpret_cast<const char*>(values.data()),
            static_cast<std::streamsize>(values.size() * sizeof(Value)));
    }
    if (!output_stream) {
        throw std::runtime_error("failed to write output: " + path);
    }
}

template <typename Value>
sa_buffer_view_v1 input_view(const std::vector<Value>& values) {
    static_assert(
        std::is_same_v<Value, double> || std::is_same_v<Value, std::uint64_t>,
        "product replay supports only f64 and u64 input vectors");
    const auto element_type =
        std::is_same_v<Value, double> ? SA_ELEMENT_TYPE_F64 : SA_ELEMENT_TYPE_U64;
    return {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_buffer_view_v1)),
        values.empty() ? nullptr : values.data(),
        values.size(),
        sizeof(Value),
        static_cast<std::uint32_t>(element_type),
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

inline sa_mut_buffer_view_v1 output_view(std::vector<double>& values) {
    return {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_mut_buffer_view_v1)),
        values.empty() ? nullptr : values.data(),
        values.size(),
        sizeof(double),
        SA_ELEMENT_TYPE_F64,
        SA_MEMORY_SPACE_HOST,
        -1,
        0U,
    };
}

inline sa_full_residual_status_v1 status_output() {
    sa_full_residual_status_v1 status {};
    status.abi_version = SA_ABI_V1_12;
    status.struct_size = static_cast<std::uint32_t>(sizeof(status));
    return status;
}

inline sa_api_v1 load_product_api() {
    const sa_api_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_api_request_v1)),
        0U,
        {0U, 0U, 0U},
    };
    sa_api_v1 api {};
    api.abi_version = SA_ABI_V1_12;
    api.struct_size = static_cast<std::uint32_t>(sizeof(api));
    ErrorBuffer error;
    require_ok(sa_get_api_v1(&request, &api, &error.view), "sa_get_api_v1", error);
    if (api.abi_version != SA_ABI_V1_12 || api.backend_get_api == nullptr) {
        throw std::runtime_error("product ABI v1.12 backend selector is unavailable");
    }
    return api;
}

inline sa_backend_api_v1 select_backend(
    const sa_api_v1& main_api,
    const std::uint32_t execution_backend,
    const std::int32_t device_id) {
    const sa_backend_request_v1 request {
        SA_ABI_V1_12,
        static_cast<std::uint32_t>(sizeof(sa_backend_request_v1)),
        execution_backend,
        device_id,
        0U,
        {0U, 0U},
    };
    sa_backend_api_v1 backend {};
    backend.abi_version = SA_ABI_V1_12;
    backend.struct_size = static_cast<std::uint32_t>(sizeof(backend));
    ErrorBuffer error;
    require_ok(
        main_api.backend_get_api(&request, &backend, &error.view),
        "select product backend",
        error);
    if (backend.execution_backend != execution_backend || backend.device_id != device_id
        || (backend.capabilities & SA_BACKEND_CAPABILITY_FULL_RESIDUAL) == 0U
        || backend.full_residual_create == nullptr
        || backend.full_residual_evaluate == nullptr
        || backend.full_residual_destroy == nullptr
        || backend.full_residual_device_name_size == nullptr
        || backend.full_residual_device_name_write == nullptr) {
        throw std::runtime_error("selected product backend contract is incomplete");
    }
    return backend;
}

struct OperatorData {
    std::vector<std::uint64_t> frame_dofs;
    std::vector<double> frame_stiffness;
    std::vector<std::uint64_t> shell_row_offsets;
    std::vector<std::uint64_t> shell_column_indices;
    std::vector<double> shell_values;
    std::vector<std::uint64_t> spring_row_offsets;
    std::vector<std::uint64_t> spring_column_indices;
    std::vector<double> spring_values;
    std::vector<double> external_force;
    std::vector<std::uint64_t> free_dofs;
    std::uint64_t frame_element_count {0U};
    std::uint64_t order {0U};
    std::uint64_t shell_nonzeros {0U};
    std::uint64_t spring_nonzeros {0U};

    sa_full_residual_operator_v1 descriptor() const {
        return {
            SA_ABI_V1_12,
            static_cast<std::uint32_t>(sizeof(sa_full_residual_operator_v1)),
            input_view(frame_dofs),
            input_view(frame_stiffness),
            input_view(shell_row_offsets),
            input_view(shell_column_indices),
            input_view(shell_values),
            input_view(spring_row_offsets),
            input_view(spring_column_indices),
            input_view(spring_values),
            input_view(external_force),
            input_view(free_dofs),
            frame_element_count,
            order,
            shell_nonzeros,
            spring_nonzeros,
            free_dofs.size(),
            {0U, 0U},
        };
    }
};

inline std::vector<std::uint64_t> identity_dofs(const std::size_t order) {
    std::vector<std::uint64_t> values(order);
    std::iota(values.begin(), values.end(), std::uint64_t {0U});
    return values;
}

inline std::vector<std::uint64_t> empty_row_offsets(const std::size_t order) {
    return std::vector<std::uint64_t>(order + 1U, 0U);
}

inline void add_zero_frame(OperatorData& operator_data) {
    operator_data.frame_element_count = 1U;
    operator_data.frame_dofs.assign(12U, 0U);
    operator_data.frame_stiffness.assign(144U, 0.0);
}

struct Evaluation {
    std::vector<double> residual;
    sa_full_residual_status_v1 status {};
};

class ProductContext {
  public:
    ProductContext(
        const OperatorData& operator_data,
        const std::uint32_t execution_backend,
        const std::int32_t device_id)
        : backend_(select_backend(load_product_api(), execution_backend, device_id)),
          creation_(status_output()) {
        auto descriptor = operator_data.descriptor();
        ErrorBuffer error;
        require_ok(
            backend_.full_residual_create(
                &descriptor,
                &context_,
                &creation_,
                &error.view),
            "create product full-residual context",
            error);
        if (context_ == nullptr || creation_.fallback_count != 0U) {
            throw std::runtime_error("product full-residual context violated no-fallback");
        }
        std::uint64_t name_size = 0U;
        error.reset();
        require_ok(
            backend_.full_residual_device_name_size(
                context_,
                &name_size,
                &error.view),
            "query product device name",
            error);
        if (name_size < 2U || name_size > 4096U) {
            throw std::runtime_error("product device name size is invalid");
        }
        std::string name(checked_count(name_size, "device name"), '\0');
        error.reset();
        require_ok(
            backend_.full_residual_device_name_write(
                context_,
                name.data(),
                name_size,
                &error.view),
            "read product device name",
            error);
        name.pop_back();
        device_name_ = std::move(name);
    }

    ProductContext(const ProductContext&) = delete;
    ProductContext& operator=(const ProductContext&) = delete;
    ProductContext(ProductContext&&) = delete;
    ProductContext& operator=(ProductContext&&) = delete;

    ~ProductContext() {
        if (context_ != nullptr) {
            ErrorBuffer error;
            (void)backend_.full_residual_destroy(context_, &error.view);
        }
    }

    Evaluation evaluate(
        const std::vector<double>& states,
        const std::uint64_t batch_size,
        const std::uint32_t repetitions,
        const std::uint64_t free_dof_count) {
        const auto output_count = checked_product(
            checked_count(batch_size, "batch size"),
            checked_count(free_dof_count, "free DOF count"),
            "residual");
        Evaluation evaluation {
            std::vector<double>(output_count, 0.0),
            status_output(),
        };
        const sa_full_residual_eval_config_v1 config {
            SA_ABI_V1_12,
            static_cast<std::uint32_t>(sizeof(sa_full_residual_eval_config_v1)),
            batch_size,
            repetitions,
            0U,
            {0U, 0U},
        };
        const auto state_view = input_view(states);
        auto residual_view = output_view(evaluation.residual);
        ErrorBuffer error;
        require_ok(
            backend_.full_residual_evaluate(
                context_,
                &config,
                &state_view,
                &residual_view,
                &evaluation.status,
                &error.view),
            "evaluate product full-residual context",
            error);
        if (evaluation.status.fallback_count != 0U
            || evaluation.status.execution_backend != backend_.execution_backend
            || evaluation.status.device_id != backend_.device_id) {
            throw std::runtime_error("product evaluation backend identity or fallback drifted");
        }
        return evaluation;
    }

    const sa_full_residual_status_v1& creation() const noexcept { return creation_; }
    const sa_backend_api_v1& backend() const noexcept { return backend_; }
    const std::string& device_name() const noexcept { return device_name_; }

  private:
    sa_backend_api_v1 backend_ {};
    sa_full_residual_context_v1* context_ {nullptr};
    sa_full_residual_status_v1 creation_ {};
    std::string device_name_;
};

inline std::uint32_t parse_backend(
    const int argc,
    char** const argv,
    const std::uint32_t default_backend = SA_EXECUTION_BACKEND_HIP) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string_view(argv[index]) == "--backend") {
            const std::string_view value(argv[index + 1]);
            if (value == "cpu") {
                return SA_EXECUTION_BACKEND_CPU;
            }
            if (value == "hip") {
                return SA_EXECUTION_BACKEND_HIP;
            }
            throw std::runtime_error("--backend must be cpu or hip");
        }
    }
    return default_backend;
}

inline std::int32_t backend_device_id(const std::uint32_t backend) {
    return backend == SA_EXECUTION_BACKEND_CPU ? -1 : 0;
}

inline const char* backend_label(const std::uint32_t backend) {
    return backend == SA_EXECUTION_BACKEND_CPU ? "cpu" : "hip";
}

inline bool self_test_requested(const int argc, char** const argv) {
    for (int index = 1; index < argc; ++index) {
        if (std::string_view(argv[index]) == "--self-test") {
            return true;
        }
    }
    return false;
}

inline int run_self_test(
    const std::string_view role,
    const std::uint32_t execution_backend) {
    OperatorData operator_data;
    operator_data.order = 1U;
    add_zero_frame(operator_data);
    operator_data.shell_row_offsets = {0U, 1U};
    operator_data.shell_column_indices = {0U};
    operator_data.shell_values = {2.0};
    operator_data.spring_row_offsets = {0U, 1U};
    operator_data.spring_column_indices = {0U};
    operator_data.spring_values = {3.0};
    operator_data.external_force = {1.0};
    operator_data.free_dofs = {0U};
    operator_data.shell_nonzeros = 1U;
    operator_data.spring_nonzeros = 1U;
    const std::vector<double> states {4.0, -2.0};

    ProductContext context(
        operator_data,
        execution_backend,
        backend_device_id(execution_backend));
    const auto first = context.evaluate(states, 2U, 2U, 1U);
    const auto second = context.evaluate(states, 2U, 2U, 1U);
    if (first.residual != std::vector<double>({19.0, -11.0})
        || first.residual != second.residual
        || first.status.fallback_count != 0U
        || second.status.fallback_count != 0U
        || (first.status.flags & SA_FULL_RESIDUAL_FP64) == 0U
        || (first.status.flags & SA_FULL_RESIDUAL_DETERMINISTIC) == 0U) {
        throw std::runtime_error("product replay self-test result drifted");
    }
    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-replay-product-link.v1\","
              << "\"ok\":true,\"role\":\"" << json_escape(role) << "\","
              << "\"single_entry_symbol\":\"sa_get_api_v1\","
              << "\"product_library_linked\":true,\"kernel_owner\":\"structural_c_abi_v1\","
              << "\"backend\":\"" << backend_label(execution_backend) << "\","
              << "\"execution_backend\":" << second.status.execution_backend << ','
              << "\"device_name\":\"" << json_escape(context.device_name()) << "\","
              << "\"repeat_bitwise\":true,\"fallback_count\":0,"
              << "\"fp64\":true,\"deterministic\":true}\n";
    return 0;
}

inline void write_metrics_json(
    std::ostream& output,
    const ProductContext& context,
    const sa_full_residual_status_v1& status) {
    output << "\"single_entry_symbol\":\"sa_get_api_v1\","
           << "\"product_library_linked\":true,"
           << "\"kernel_owner\":\"structural_c_abi_v1\","
           << "\"execution_backend\":" << status.execution_backend << ','
           << "\"device_id\":" << status.device_id << ','
           << "\"device_name\":\"" << json_escape(context.device_name()) << "\","
           << "\"fallback_count\":" << status.fallback_count << ','
           << "\"operator_buffers_device_resident\":"
           << (((context.creation().flags & SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT) != 0U)
                   ? "true"
                   : "false")
           << ','
           << "\"eval_buffers_reused\":"
           << (((status.flags & SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED) != 0U)
                   ? "true"
                   : "false")
           << ','
           << "\"fp64\":"
           << (((status.flags & SA_FULL_RESIDUAL_FP64) != 0U) ? "true" : "false")
           << ','
           << "\"deterministic\":"
           << (((status.flags & SA_FULL_RESIDUAL_DETERMINISTIC) != 0U) ? "true" : "false")
           << ','
           << "\"h2d_bytes\":" << status.h2d_bytes << ','
           << "\"d2h_bytes\":" << status.d2h_bytes << ','
           << "\"h2d_transfer_count\":" << status.h2d_transfer_count << ','
           << "\"d2h_transfer_count\":" << status.d2h_transfer_count << ','
           << "\"synchronization_count\":" << status.synchronization_count << ','
           << "\"kernel_launch_count\":" << status.kernel_launch_count << ','
           << "\"device_buffer_bytes\":" << status.device_buffer_bytes << ','
           << "\"vram_total_bytes\":" << status.vram_total_bytes << ','
           << "\"vram_free_before_bytes\":" << status.vram_free_before_bytes << ','
           << "\"vram_free_after_bytes\":" << status.vram_free_after_bytes << ','
           << "\"kernel_elapsed_ms_total\":" << status.kernel_elapsed_ms_total << ','
           << "\"kernel_elapsed_ms_mean\":" << status.kernel_elapsed_ms_mean << ','
           << "\"output_abs_sum\":" << status.output_abs_sum << ','
           << "\"output_max_abs\":" << status.output_max_abs;
}

}  // namespace structural::compatibility::replay

#endif

