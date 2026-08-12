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
    std::string dofs_path;
    std::string stiffness_path;
    std::string states_path;
    std::string output_path;
    std::uint64_t element_count {0U};
    std::uint64_t order {0U};
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
        if (key == "--dofs") {
            args.dofs_path = next();
        } else if (key == "--stiffness") {
            args.stiffness_path = next();
        } else if (key == "--states") {
            args.states_path = next();
        } else if (key == "--output") {
            args.output_path = next();
        } else if (key == "--element-count") {
            args.element_count = std::stoull(next());
        } else if (key == "--n-dof") {
            args.order = std::stoull(next());
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
    if (args.dofs_path.empty() || args.stiffness_path.empty()
        || args.states_path.empty() || args.output_path.empty()
        || args.element_count == 0U || args.order == 0U || args.batch_size == 0U) {
        throw std::runtime_error("missing required arguments");
    }
    return args;
}
replay::OperatorData load_operator(const Args& args) {
    replay::OperatorData operator_data;
    operator_data.frame_element_count = args.element_count;
    operator_data.order = args.order;
    const auto element_count = replay::checked_count(args.element_count, "element count");
    const auto order = replay::checked_count(args.order, "order");
    operator_data.frame_dofs = replay::read_binary<std::uint64_t>(
        args.dofs_path,
        replay::checked_product(element_count, 12U, "frame DOFs"));
    operator_data.frame_stiffness = replay::read_binary<double>(
        args.stiffness_path,
        replay::checked_product(element_count, 144U, "frame stiffness"));
    operator_data.shell_row_offsets = replay::empty_row_offsets(order);
    operator_data.spring_row_offsets = replay::empty_row_offsets(order);
    operator_data.external_force.assign(order, 0.0);
    operator_data.free_dofs = replay::identity_dofs(order);
    return operator_data;
}

}  // namespace

int main(const int argc, char** const argv) {
    try {
        const auto execution_backend = replay::parse_backend(argc, argv);
        if (replay::self_test_requested(argc, argv)) {
            return replay::run_self_test("frame_force_batch", execution_backend);
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
        const auto evaluation =
            context.evaluate(states, args.batch_size, args.repetitions, args.order);
        replay::write_binary(args.output_path, evaluation.residual);

        std::cout << std::setprecision(17)
                  << "{\"ok\":true,"
                  << "\"backend\":\"native_"
                  << replay::backend_label(args.execution_backend)
                  << "_frame_force_batch_product_adapter\","
                  << "\"element_count\":" << args.element_count << ','
                  << "\"n_dof\":" << args.order << ','
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
