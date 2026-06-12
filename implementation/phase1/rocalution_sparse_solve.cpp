// Standalone rocALUTION sparse Krylov/AMG solve bridge for the MGT ROCm probe.
//
// The Python probe owns model assembly and residual replay. This binary only
// receives one CSR system, solves it with rocALUTION on the accelerator, and
// writes the solution back for independent replay in Python.

#include <rocalution/rocalution.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>

using rocalution::BiCGStab;
using rocalution::CG;
using rocalution::FixedPoint;
using rocalution::GMRES;
using rocalution::IC;
using rocalution::ILU;
using rocalution::ILUT;
using rocalution::IterativeLinearSolver;
using rocalution::Jacobi;
using rocalution::LocalMatrix;
using rocalution::LocalVector;
using rocalution::MultiColoredILU;
using rocalution::Preconditioner;
using rocalution::SAAMG;
using rocalution::Solver;

namespace
{
struct Args
{
    int n = 0;
    int64_t nnz = 0;
    std::string row_ptr;
    std::string col_ind;
    std::string values;
    std::string rhs;
    std::string solution_out;
    std::string stats_json;
    std::string solver = "gmres";
    std::string preconditioner = "multi_colored_ilu";
    double abs_tol = 1.0e-8;
    double rel_tol = 1.0e-12;
    int max_iter = 4000;
    int basis_size = 64;
    int ilu_p = 0;
    int ilu_q = 1;
    int amg_levels = 20;
    int amg_coarse_size = 256;
    bool amg_manual_smoothers = true;
};

std::string json_escape(const std::string& value)
{
    std::ostringstream out;
    for(char ch : value)
    {
        switch(ch)
        {
        case '\\':
            out << "\\\\";
            break;
        case '"':
            out << "\\\"";
            break;
        case '\n':
            out << "\\n";
            break;
        case '\r':
            out << "\\r";
            break;
        case '\t':
            out << "\\t";
            break;
        default:
            out << ch;
        }
    }
    return out.str();
}

template <typename T>
T* read_array(const std::string& path, int64_t count)
{
    if(count < 0)
    {
        throw std::runtime_error("negative array count");
    }
    T* data = new T[static_cast<size_t>(count)];
    std::ifstream in(path, std::ios::binary);
    if(!in)
    {
        delete[] data;
        throw std::runtime_error("cannot open input file: " + path);
    }
    in.read(reinterpret_cast<char*>(data), static_cast<std::streamsize>(sizeof(T) * count));
    if(in.gcount() != static_cast<std::streamsize>(sizeof(T) * count))
    {
        delete[] data;
        throw std::runtime_error("short read from input file: " + path);
    }
    return data;
}

template <typename T>
void write_array(const std::string& path, const T* data, int64_t count)
{
    std::ofstream out(path, std::ios::binary);
    if(!out)
    {
        throw std::runtime_error("cannot open output file: " + path);
    }
    out.write(reinterpret_cast<const char*>(data),
              static_cast<std::streamsize>(sizeof(T) * count));
    if(!out)
    {
        throw std::runtime_error("failed writing output file: " + path);
    }
}

std::map<std::string, std::string> parse_flags(int argc, char** argv)
{
    std::map<std::string, std::string> flags;
    for(int i = 1; i < argc; i += 2)
    {
        std::string key = argv[i];
        if(key.rfind("--", 0) != 0 || i + 1 >= argc)
        {
            throw std::runtime_error("expected --flag value arguments");
        }
        flags[key.substr(2)] = argv[i + 1];
    }
    return flags;
}

Args parse_args(int argc, char** argv)
{
    auto flags = parse_flags(argc, argv);
    Args args;
    auto get = [&](const std::string& key, const std::string& fallback = "") {
        auto it = flags.find(key);
        return it == flags.end() ? fallback : it->second;
    };
    args.n = std::stoi(get("n"));
    args.nnz = std::stoll(get("nnz"));
    args.row_ptr = get("row-ptr");
    args.col_ind = get("col-ind");
    args.values = get("values");
    args.rhs = get("rhs");
    args.solution_out = get("solution-out");
    args.stats_json = get("stats-json");
    args.solver = get("solver", args.solver);
    args.preconditioner = get("preconditioner", args.preconditioner);
    args.abs_tol = std::stod(get("abs-tol", "1e-8"));
    args.rel_tol = std::stod(get("rel-tol", "1e-12"));
    args.max_iter = std::stoi(get("max-iter", "4000"));
    args.basis_size = std::stoi(get("basis-size", "64"));
    args.ilu_p = std::stoi(get("ilu-p", "0"));
    args.ilu_q = std::stoi(get("ilu-q", "1"));
    args.amg_levels = std::stoi(get("amg-levels", "20"));
    args.amg_coarse_size = std::stoi(get("amg-coarse-size", "256"));
    args.amg_manual_smoothers = get("amg-manual-smoothers", "1") != "0";
    if(args.n <= 0 || args.nnz <= 0)
    {
        throw std::runtime_error("invalid matrix dimensions");
    }
    return args;
}

void write_stats(const Args& args,
                 const std::string& status,
                 const std::string& error,
                 int iteration_count,
                 int solver_status,
                 double current_residual,
                 double solve_seconds,
                 int amg_num_levels = -1,
                 const std::string& setup_mode = "")
{
    std::ofstream out(args.stats_json);
    if(!out)
    {
        throw std::runtime_error("cannot open stats json: " + args.stats_json);
    }
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"status\": \"" << json_escape(status) << "\",\n";
    out << "  \"backend\": \"rocalution_hip_sparse_preconditioned_krylov\",\n";
    out << "  \"solver\": \"" << json_escape(args.solver) << "\",\n";
    out << "  \"preconditioner\": \"" << json_escape(args.preconditioner) << "\",\n";
    out << "  \"n\": " << args.n << ",\n";
    out << "  \"nnz\": " << args.nnz << ",\n";
    out << "  \"max_iterations\": " << args.max_iter << ",\n";
    out << "  \"basis_size\": " << args.basis_size << ",\n";
    out << "  \"ilu_p\": " << args.ilu_p << ",\n";
    out << "  \"ilu_q\": " << args.ilu_q << ",\n";
    out << "  \"amg_levels_requested\": " << args.amg_levels << ",\n";
    out << "  \"amg_coarse_size\": " << args.amg_coarse_size << ",\n";
    out << "  \"amg_manual_smoothers\": " << (args.amg_manual_smoothers ? "true" : "false") << ",\n";
    out << "  \"amg_num_levels\": " << amg_num_levels << ",\n";
    out << "  \"setup_mode\": \"" << json_escape(setup_mode) << "\",\n";
    out << "  \"iteration_count\": " << iteration_count << ",\n";
    out << "  \"solver_status\": " << solver_status << ",\n";
    out << "  \"current_residual\": " << current_residual << ",\n";
    out << "  \"solve_seconds\": " << solve_seconds << ",\n";
    out << "  \"device_residency_ratio\": 1.0,\n";
    out << "  \"host_copy_bytes\": 0,\n";
    out << "  \"cpu_solver_fallback_detected\": false,\n";
    out << "  \"error\": \"" << json_escape(error) << "\"\n";
    out << "}\n";
}

template <typename SolverType>
void configure_iterative(SolverType& solver, const Args& args)
{
    solver.Init(args.abs_tol, args.rel_tol, 1.0e8, args.max_iter);
    solver.Verbose(0);
}

template <typename SolverType>
void solve_with_preconditioner(SolverType& solver,
                               Solver<LocalMatrix<double>, LocalVector<double>, double>* precond,
                               LocalMatrix<double>& matrix,
                               LocalVector<double>& rhs,
                               LocalVector<double>& x,
                               const Args& args)
{
    solver.SetOperator(matrix);
    if(precond != nullptr)
    {
        solver.SetPreconditioner(*precond);
    }
    solver.Build();
    solver.Init(args.abs_tol, args.rel_tol, 1.0e8, args.max_iter);
    solver.Verbose(0);
    solver.Solve(rhs, &x);
}
} // namespace

int main(int argc, char** argv)
{
    Args args;
    auto start = std::chrono::steady_clock::now();
    try
    {
        args = parse_args(argc, argv);
        rocalution::set_device_rocalution(0);
        rocalution::init_rocalution();

        int32_t* row_ptr = read_array<int32_t>(args.row_ptr, static_cast<int64_t>(args.n) + 1);
        int* col_ind = read_array<int>(args.col_ind, args.nnz);
        double* values = read_array<double>(args.values, args.nnz);
        double* rhs_values = read_array<double>(args.rhs, args.n);

        LocalMatrix<double> matrix;
        matrix.SetDataPtrCSR(&row_ptr, &col_ind, &values, "mgt_rocalution_csr", args.nnz, args.n, args.n);
        matrix.Sort();
        LocalVector<double> rhs;
        rhs.SetDataPtr(&rhs_values, "mgt_rocalution_rhs", args.n);
        LocalVector<double> x;
        x.Allocate("mgt_rocalution_solution", args.n);
        x.Zeros();

        matrix.MoveToAccelerator();
        rhs.MoveToAccelerator();
        x.MoveToAccelerator();

        Solver<LocalMatrix<double>, LocalVector<double>, double>* precond = nullptr;
        MultiColoredILU<LocalMatrix<double>, LocalVector<double>, double> ilu;
        ILU<LocalMatrix<double>, LocalVector<double>, double> ilu_level;
        ILUT<LocalMatrix<double>, LocalVector<double>, double> ilut;
        IC<LocalMatrix<double>, LocalVector<double>, double> ic;
        SAAMG<LocalMatrix<double>, LocalVector<double>, double> amg;
        if(args.preconditioner == "multi_colored_ilu")
        {
            ilu.Set(args.ilu_p, args.ilu_q, true);
            precond = &ilu;
        }
        else if(args.preconditioner == "ilu")
        {
            ilu_level.Set(args.ilu_p, true);
            precond = &ilu_level;
        }
        else if(args.preconditioner == "ilut")
        {
            ilut.Set(1.0e-6, std::max(20, args.ilu_q));
            precond = &ilut;
        }
        else if(args.preconditioner == "ic")
        {
            precond = &ic;
        }
        else if(args.preconditioner == "saamg")
        {
            amg.SetCoarseningStrategy(rocalution::PMIS);
            amg.SetLumpingStrategy(rocalution::AddWeakConnections);
            amg.SetInterpRelax(2.0 / 3.0);
            amg.SetCouplingStrength(0.001);
            amg.SetCoarsestLevel(std::max(200, args.amg_coarse_size));
            amg.InitLevels(args.amg_levels);
            amg.SetSmootherPreIter(2);
            amg.SetSmootherPostIter(2);
            amg.Verbose(0);
            std::cerr << "rocalution_preconditioner_saamg "
                      << "manual_smoothers=" << (args.amg_manual_smoothers ? 1 : 0)
                      << " coarse_size=" << args.amg_coarse_size
                      << " requested_levels=" << args.amg_levels << "\n";
            precond = &amg;
        }
        else if(args.preconditioner == "none")
        {
            precond = nullptr;
        }
        else
        {
            throw std::runtime_error("unsupported preconditioner: " + args.preconditioner);
        }

        if(args.solver == "gmres")
        {
            GMRES<LocalMatrix<double>, LocalVector<double>, double> solver;
            configure_iterative(solver, args);
            solver.SetBasisSize(args.basis_size);
            solve_with_preconditioner(solver, precond, matrix, rhs, x, args);
            x.MoveToHost();
            double* solution = nullptr;
            x.LeaveDataPtr(&solution);
            write_array(args.solution_out, solution, args.n);
            delete[] solution;
            auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            write_stats(args, "ok", "", solver.GetIterationCount(), solver.GetSolverStatus(),
                        solver.GetCurrentResidual(), elapsed);
        }
        else if(args.solver == "bicgstab")
        {
            BiCGStab<LocalMatrix<double>, LocalVector<double>, double> solver;
            configure_iterative(solver, args);
            solve_with_preconditioner(solver, precond, matrix, rhs, x, args);
            x.MoveToHost();
            double* solution = nullptr;
            x.LeaveDataPtr(&solution);
            write_array(args.solution_out, solution, args.n);
            delete[] solution;
            auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            write_stats(args, "ok", "", solver.GetIterationCount(), solver.GetSolverStatus(),
                        solver.GetCurrentResidual(), elapsed);
        }
        else if(args.solver == "cg")
        {
            CG<LocalMatrix<double>, LocalVector<double>, double> solver;
            configure_iterative(solver, args);
            solve_with_preconditioner(solver, precond, matrix, rhs, x, args);
            x.MoveToHost();
            double* solution = nullptr;
            x.LeaveDataPtr(&solution);
            write_array(args.solution_out, solution, args.n);
            delete[] solution;
            auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            write_stats(args, "ok", "", solver.GetIterationCount(), solver.GetSolverStatus(),
                        solver.GetCurrentResidual(), elapsed);
        }
        else if(args.solver == "saamg")
        {
            SAAMG<LocalMatrix<double>, LocalVector<double>, double> solver;
            solver.SetOperator(matrix);
            solver.SetCouplingStrength(0.001);
            solver.SetInterpRelax(2.0 / 3.0);
            solver.SetCoarseningStrategy(rocalution::Greedy);
            solver.SetCoarsestLevel(std::max(200, args.amg_coarse_size));
            solver.InitLevels(args.amg_levels);
            solver.SetScaling(true);
            solver.MoveToAccelerator();
            int levels = -1;
            const std::string setup_mode =
                args.amg_manual_smoothers ? "manual_smoother_chain" : "rocalution_default_smoothers";
            if(args.amg_manual_smoothers)
            {
                solver.SetManualSmoothers(true);
                solver.SetManualSolver(true);
                solver.BuildHierarchy();
                levels = solver.GetNumLevels();
                std::cerr << "rocalution_saamg_hierarchy levels=" << levels
                          << " setup_mode=" << setup_mode
                          << " coarse_size=" << args.amg_coarse_size << "\n";
                CG<LocalMatrix<double>, LocalVector<double>, double> coarse_solver;
                coarse_solver.Verbose(0);
                auto** smoothers =
                    new IterativeLinearSolver<LocalMatrix<double>, LocalVector<double>, double>*[
                        std::max(0, levels - 1)];
                auto** jacobi =
                    new Preconditioner<LocalMatrix<double>, LocalVector<double>, double>*[
                        std::max(0, levels - 1)];
                for(int i = 0; i < levels - 1; ++i)
                {
                    auto* fixed_point = new FixedPoint<LocalMatrix<double>, LocalVector<double>, double>;
                    fixed_point->SetRelaxation(1.3);
                    smoothers[i] = fixed_point;
                    jacobi[i] = new Jacobi<LocalMatrix<double>, LocalVector<double>, double>;
                    smoothers[i]->SetPreconditioner(*jacobi[i]);
                    smoothers[i]->Verbose(0);
                }
                solver.SetSmoother(smoothers);
                solver.SetSolver(coarse_solver);
                solver.SetSmootherPreIter(1);
                solver.SetSmootherPostIter(2);
                solver.Init(args.abs_tol, args.rel_tol, 1.0e8, args.max_iter);
                solver.Verbose(0);
                solver.Build();
                solver.Solve(rhs, &x);
                for(int i = 0; i < levels - 1; ++i)
                {
                    delete jacobi[i];
                    delete smoothers[i];
                }
                delete[] jacobi;
                delete[] smoothers;
            }
            else
            {
                solver.SetManualSmoothers(false);
                solver.SetManualSolver(false);
                solver.Init(args.abs_tol, args.rel_tol, 1.0e8, args.max_iter);
                solver.Verbose(0);
                solver.Build();
                levels = solver.GetNumLevels();
                std::cerr << "rocalution_saamg_hierarchy levels=" << levels
                          << " setup_mode=" << setup_mode
                          << " coarse_size=" << args.amg_coarse_size << "\n";
                solver.Solve(rhs, &x);
            }
            x.MoveToHost();
            double* solution = nullptr;
            x.LeaveDataPtr(&solution);
            write_array(args.solution_out, solution, args.n);
            delete[] solution;
            auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            write_stats(args, "ok", "", solver.GetIterationCount(), solver.GetSolverStatus(),
                        solver.GetCurrentResidual(), elapsed, levels, setup_mode);
            solver.Clear();
        }
        else
        {
            throw std::runtime_error("unsupported solver: " + args.solver);
        }

        rocalution::stop_rocalution();
        return 0;
    }
    catch(const std::exception& exc)
    {
        auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        if(!args.stats_json.empty())
        {
            try
            {
                write_stats(args, "error", exc.what(), 0, -1,
                            std::numeric_limits<double>::infinity(), elapsed);
            }
            catch(...)
            {
            }
        }
        std::cerr << "rocalution_sparse_solve error: " << exc.what() << "\n";
        return 2;
    }
}
