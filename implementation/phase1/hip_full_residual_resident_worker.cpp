#include "product_full_residual_replay.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace replay = structural::compatibility::replay;

namespace {

struct Args {
    std::string frame_dofs_path;
    std::string frame_stiffness_path;
    std::string shell_row_ptr_path;
    std::string shell_col_idx_path;
    std::string shell_values_path;
    std::string spring_row_ptr_path;
    std::string spring_col_idx_path;
    std::string spring_values_path;
    std::string external_force_path;
    std::string free_path;
    std::uint64_t frame_element_count {0U};
    std::uint64_t order {0U};
    std::uint64_t shell_nonzeros {0U};
    std::uint64_t spring_nonzeros {0U};
    std::uint64_t free_dof_count {0U};
    std::uint32_t execution_backend {SA_EXECUTION_BACKEND_HIP};
};

Args parse_args(const int argc, char** const argv) {
    Args args;
    args.execution_backend = replay::parse_backend(argc, argv);
    for (int index = 1; index < argc; ++index) {
        const std::string key(argv[index]);
        auto next = [&]() -> std::string {
            if (index + 1 >= argc) {
                throw std::runtime_error("missing value for " + key);
            }
            return std::string(argv[++index]);
        };
        if (key == "--frame-dofs") {
            args.frame_dofs_path = next();
        } else if (key == "--frame-stiffness") {
            args.frame_stiffness_path = next();
        } else if (key == "--shell-row-ptr") {
            args.shell_row_ptr_path = next();
        } else if (key == "--shell-col-idx") {
            args.shell_col_idx_path = next();
        } else if (key == "--shell-values") {
            args.shell_values_path = next();
        } else if (key == "--spring-row-ptr") {
            args.spring_row_ptr_path = next();
        } else if (key == "--spring-col-idx") {
            args.spring_col_idx_path = next();
        } else if (key == "--spring-values") {
            args.spring_values_path = next();
        } else if (key == "--f-ext") {
            args.external_force_path = next();
        } else if (key == "--free") {
            args.free_path = next();
        } else if (key == "--frame-element-count") {
            args.frame_element_count = std::stoull(next());
        } else if (key == "--n-dof") {
            args.order = std::stoull(next());
        } else if (key == "--shell-nnz") {
            args.shell_nonzeros = std::stoull(next());
        } else if (key == "--spring-nnz") {
            args.spring_nonzeros = std::stoull(next());
        } else if (key == "--free-count") {
            args.free_dof_count = std::stoull(next());
        } else if (key == "--backend") {
            (void)next();
        } else {
            throw std::runtime_error("unknown argument: " + key);
        }
    }
    const bool missing_paths =
        args.frame_dofs_path.empty() || args.frame_stiffness_path.empty()
        || args.shell_row_ptr_path.empty() || args.shell_col_idx_path.empty()
        || args.shell_values_path.empty() || args.spring_row_ptr_path.empty()
        || args.spring_col_idx_path.empty() || args.spring_values_path.empty()
        || args.external_force_path.empty() || args.free_path.empty();
    if (missing_paths || args.frame_element_count == 0U || args.order == 0U
        || args.free_dof_count == 0U) {
        throw std::runtime_error("missing required arguments");
    }
    return args;
}
replay::OperatorData load_operator(const Args& args) {
    replay::OperatorData operator_data;
    operator_data.frame_element_count = args.frame_element_count;
    operator_data.order = args.order;
    operator_data.shell_nonzeros = args.shell_nonzeros;
    operator_data.spring_nonzeros = args.spring_nonzeros;
    const auto frame_count = replay::checked_count(args.frame_element_count, "frame element count");
    const auto order = replay::checked_count(args.order, "order");
    operator_data.frame_dofs = replay::read_binary<std::uint64_t>(
        args.frame_dofs_path,
        replay::checked_product(frame_count, 12U, "frame DOFs"));
    operator_data.frame_stiffness = replay::read_binary<double>(
        args.frame_stiffness_path,
        replay::checked_product(frame_count, 144U, "frame stiffness"));
    operator_data.shell_row_offsets =
        replay::read_binary<std::uint64_t>(args.shell_row_ptr_path, order + 1U);
    operator_data.shell_column_indices = replay::read_binary<std::uint64_t>(
        args.shell_col_idx_path,
        replay::checked_count(args.shell_nonzeros, "shell nonzeros"));
    operator_data.shell_values = replay::read_binary<double>(
        args.shell_values_path,
        replay::checked_count(args.shell_nonzeros, "shell nonzeros"));
    operator_data.spring_row_offsets =
        replay::read_binary<std::uint64_t>(args.spring_row_ptr_path, order + 1U);
    operator_data.spring_column_indices = replay::read_binary<std::uint64_t>(
        args.spring_col_idx_path,
        replay::checked_count(args.spring_nonzeros, "spring nonzeros"));
    operator_data.spring_values = replay::read_binary<double>(
        args.spring_values_path,
        replay::checked_count(args.spring_nonzeros, "spring nonzeros"));
    operator_data.external_force =
        replay::read_binary<double>(args.external_force_path, order);
    operator_data.free_dofs = replay::read_binary<std::uint64_t>(
        args.free_path,
        replay::checked_count(args.free_dof_count, "free DOF count"));
    return operator_data;
}

void evaluate_request(
    replay::ProductContext& context,
    const Args& args,
    const std::string& states_path,
    const std::string& output_path,
    const std::uint64_t batch_size,
    const std::uint32_t repetitions,
    const std::uint64_t request_id) {
    if (batch_size == 0U) {
        throw std::runtime_error("batch size must be positive");
    }
    const auto state_count = replay::checked_product(
        replay::checked_count(batch_size, "batch size"),
        replay::checked_count(args.order, "order"),
        "states");
    const auto states = replay::read_binary<double>(states_path, state_count);
    const auto evaluation =
        context.evaluate(states, batch_size, repetitions, args.free_dof_count);
    replay::write_binary(output_path, evaluation.residual);

    std::cout << std::setprecision(17)
              << "{\"ok\":true,"
              << "\"backend\":\"native_"
              << replay::backend_label(args.execution_backend)
              << "_full_residual_resident_worker_product_adapter\","
              << "\"request_id\":" << request_id << ','
              << "\"frame_element_count\":" << args.frame_element_count << ','
              << "\"n_dof\":" << args.order << ','
              << "\"free_count\":" << args.free_dof_count << ','
              << "\"shell_nnz\":" << args.shell_nonzeros << ','
              << "\"spring_nnz\":" << args.spring_nonzeros << ','
              << "\"batch_size\":" << batch_size << ','
              << "\"reps\":" << repetitions << ',';
    replay::write_metrics_json(std::cout, context, evaluation.status);
    std::cout << "}" << std::endl;
}

}  // namespace

int main(const int argc, char** const argv) {
    try {
        const auto execution_backend = replay::parse_backend(argc, argv);
        if (replay::self_test_requested(argc, argv)) {
            return replay::run_self_test("full_residual_resident_worker", execution_backend);
        }
        const auto args = parse_args(argc, argv);
        const auto operator_data = load_operator(args);
        replay::ProductContext context(
            operator_data,
            args.execution_backend,
            replay::backend_device_id(args.execution_backend));

        std::cout << "{\"ok\":true,"
                  << "\"backend\":\"native_"
                  << replay::backend_label(args.execution_backend)
                  << "_full_residual_resident_worker_product_adapter\","
                  << "\"status\":\"ready\","
                  << "\"single_entry_symbol\":\"sa_get_api_v1\","
                  << "\"product_library_linked\":true,"
                  << "\"kernel_owner\":\"structural_c_abi_v1\","
                  << "\"execution_backend\":" << context.backend().execution_backend << ','
                  << "\"device_id\":" << context.backend().device_id << ','
                  << "\"device_name\":\"" << replay::json_escape(context.device_name()) << "\","
                  << "\"fallback_count\":" << context.creation().fallback_count << ','
                  << "\"operator_buffers_device_resident\":"
                  << (((context.creation().flags & SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT) != 0U)
                          ? "true"
                          : "false")
                  << ",\"frame_element_count\":" << args.frame_element_count
                  << ",\"n_dof\":" << args.order
                  << ",\"free_count\":" << args.free_dof_count
                  << ",\"shell_nnz\":" << args.shell_nonzeros
                  << ",\"spring_nnz\":" << args.spring_nonzeros
                  << "}" << std::endl;

        std::string line;
        std::uint64_t request_id = 0U;
        while (std::getline(std::cin, line)) {
            if (line.empty()) {
                continue;
            }
            std::istringstream command_stream(line);
            std::string command;
            command_stream >> command;
            if (command == "QUIT" || command == "quit") {
                std::cout
                    << "{\"ok\":true,\"status\":\"bye\","
                    << "\"backend\":\"product_full_residual_resident_worker\"}"
                    << std::endl;
                break;
            }
            if (command != "EVAL") {
                std::cout << "{\"ok\":false,\"error\":\"unknown command\",\"line\":\""
                          << replay::json_escape(line) << "\"}" << std::endl;
                continue;
            }
            std::string states_path;
            std::string output_path;
            std::uint64_t batch_size = 0U;
            std::uint32_t repetitions = 1U;
            command_stream >> states_path >> output_path >> batch_size >> repetitions;
            if (!command_stream) {
                std::cout << "{\"ok\":false,\"error\":\"bad EVAL command\",\"line\":\""
                          << replay::json_escape(line) << "\"}" << std::endl;
                continue;
            }
            ++request_id;
            try {
                evaluate_request(
                    context,
                    args,
                    states_path,
                    output_path,
                    batch_size,
                    std::max(1U, repetitions),
                    request_id);
            } catch (const std::exception& exception) {
                std::cout << "{\"ok\":false,\"request_id\":" << request_id
                          << ",\"error\":\""
                          << replay::json_escape(exception.what()) << "\"}"
                          << std::endl;
            }
        }
        return EXIT_SUCCESS;
    } catch (const std::exception& exception) {
        std::cerr << "{\"ok\":false,\"error\":\""
                  << replay::json_escape(exception.what()) << "\"}" << std::endl;
        return EXIT_FAILURE;
    }
}
