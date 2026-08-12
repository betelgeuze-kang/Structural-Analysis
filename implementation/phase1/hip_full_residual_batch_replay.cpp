#include "product_full_residual_replay.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
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
    std::string states_path;
    std::string external_force_path;
    std::string free_path;
    std::string output_path;
    std::uint64_t frame_element_count {0U};
    std::uint64_t order {0U};
    std::uint64_t shell_nonzeros {0U};
    std::uint64_t spring_nonzeros {0U};
    std::uint64_t free_dof_count {0U};
    std::uint64_t batch_size {0U};
    std::uint32_t repetitions {20U};
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
        } else if (key == "--states") {
            args.states_path = next();
        } else if (key == "--f-ext") {
            args.external_force_path = next();
        } else if (key == "--free") {
            args.free_path = next();
        } else if (key == "--output") {
            args.output_path = next();
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
        } else if (key == "--batch-size") {
            args.batch_size = std::stoull(next());
        } else if (key == "--reps") {
            args.repetitions = std::max(1U, static_cast<std::uint32_t>(std::stoul(next())));
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
        || args.states_path.empty() || args.external_force_path.empty()
        || args.free_path.empty() || args.output_path.empty();
    if (missing_paths || args.frame_element_count == 0U || args.order == 0U
        || args.free_dof_count == 0U || args.batch_size == 0U) {
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

}  // namespace

int main(const int argc, char** const argv) {
    try {
        const auto execution_backend = replay::parse_backend(argc, argv);
        if (replay::self_test_requested(argc, argv)) {
            return replay::run_self_test("full_residual_batch", execution_backend);
        }
        const auto args = parse_args(argc, argv);
        const auto operator_data = load_operator(args);
        const auto state_count = replay::checked_product(
            replay::checked_count(args.batch_size, "batch size"),
            replay::checked_count(args.order, "order"),
            "states");
        const auto states = replay::read_binary<double>(args.states_path, state_count);
        replay::ProductContext context(
            operator_data,
            args.execution_backend,
            replay::backend_device_id(args.execution_backend));
        const auto evaluation = context.evaluate(
            states,
            args.batch_size,
            args.repetitions,
            args.free_dof_count);
        replay::write_binary(args.output_path, evaluation.residual);

        std::cout << std::setprecision(17)
                  << "{\"ok\":true,"
                  << "\"backend\":\"native_"
                  << replay::backend_label(args.execution_backend)
                  << "_full_residual_batch_product_adapter\","
                  << "\"frame_element_count\":" << args.frame_element_count << ','
                  << "\"n_dof\":" << args.order << ','
                  << "\"free_count\":" << args.free_dof_count << ','
                  << "\"shell_nnz\":" << args.shell_nonzeros << ','
                  << "\"spring_nnz\":" << args.spring_nonzeros << ','
                  << "\"batch_size\":" << args.batch_size << ','
                  << "\"reps\":" << args.repetitions << ',';
        replay::write_metrics_json(std::cout, context, evaluation.status);
        std::cout << "}\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& exception) {
        std::cerr << "{\"ok\":false,\"error\":\""
                  << replay::json_escape(exception.what()) << "\"}\n";
        return EXIT_FAILURE;
    }
}
