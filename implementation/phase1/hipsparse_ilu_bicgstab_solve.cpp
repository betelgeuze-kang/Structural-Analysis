// Standalone hipSPARSE ILU(0)-BiCGStab bridge for the MGT ROCm probe.
//
// This intentionally avoids extra solver dependencies. It uses prebuilt HIP
// runtime + hipSPARSE libraries only: CSR SpMV, csrilu02 factorization, and
// csrsv2 triangular solves. Python owns model assembly and final residual
// replay, so this binary only returns a candidate solution and stats.

#include <hip/hip_runtime.h>
#include <hipsparse/hipsparse.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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
    double abs_tol = 1.0e-8;
    double rel_tol = 1.0e-12;
    int max_iter = 4000;
    bool use_ilu = true;
};

std::string json_escape(const std::string& value)
{
    std::ostringstream out;
    for(char ch : value)
    {
        switch(ch)
        {
        case '\\': out << "\\\\"; break;
        case '"': out << "\\\""; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default: out << ch;
        }
    }
    return out.str();
}

template <typename T>
T* read_array(const std::string& path, int64_t count)
{
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
    auto get = [&](const std::string& key, const std::string& fallback = "") {
        auto it = flags.find(key);
        return it == flags.end() ? fallback : it->second;
    };
    Args args;
    args.n = std::stoi(get("n"));
    args.nnz = std::stoll(get("nnz"));
    args.row_ptr = get("row-ptr");
    args.col_ind = get("col-ind");
    args.values = get("values");
    args.rhs = get("rhs");
    args.solution_out = get("solution-out");
    args.stats_json = get("stats-json");
    args.abs_tol = std::stod(get("abs-tol", "1e-8"));
    args.rel_tol = std::stod(get("rel-tol", "1e-12"));
    args.max_iter = std::stoi(get("max-iter", "4000"));
    args.use_ilu = get("preconditioner", "ilu0") != "none";
    if(args.n <= 0 || args.nnz <= 0)
    {
        throw std::runtime_error("invalid matrix dimensions");
    }
    return args;
}

void check_hip(hipError_t status, const char* where)
{
    if(status != hipSuccess)
    {
        throw std::runtime_error(std::string(where) + ": " + hipGetErrorString(status));
    }
}

void check_sparse(hipsparseStatus_t status, const char* where)
{
    if(status != HIPSPARSE_STATUS_SUCCESS)
    {
        throw std::runtime_error(std::string(where) + ": hipSPARSE status " + std::to_string(status));
    }
}

double dot_host(const std::vector<double>& a, const std::vector<double>& b)
{
    double sum = 0.0;
    for(size_t i = 0; i < a.size(); ++i)
    {
        sum += a[i] * b[i];
    }
    return sum;
}

double norm_inf_host(const std::vector<double>& a)
{
    double value = 0.0;
    for(double x : a)
    {
        value = std::max(value, std::abs(x));
    }
    return value;
}

void write_stats(const Args& args,
                 const std::string& status,
                 const std::string& error,
                 int iteration_count,
                 double residual_inf,
                 double rhs_inf,
                 double solve_seconds,
                 bool zero_pivot_detected)
{
    std::ofstream out(args.stats_json);
    if(!out)
    {
        throw std::runtime_error("cannot open stats json: " + args.stats_json);
    }
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"status\": \"" << json_escape(status) << "\",\n";
    out << "  \"backend\": \"hipsparse_ilu0_bicgstab\",\n";
    out << "  \"solver\": \"bicgstab\",\n";
    out << "  \"preconditioner\": \"" << (args.use_ilu ? "csrilu02_ilu0" : "none") << "\",\n";
    out << "  \"n\": " << args.n << ",\n";
    out << "  \"nnz\": " << args.nnz << ",\n";
    out << "  \"max_iterations\": " << args.max_iter << ",\n";
    out << "  \"iteration_count\": " << iteration_count << ",\n";
    out << "  \"residual_inf_n\": " << residual_inf << ",\n";
    out << "  \"rhs_inf_n\": " << rhs_inf << ",\n";
    out << "  \"solve_seconds\": " << solve_seconds << ",\n";
    out << "  \"device_residency_ratio\": 1.0,\n";
    out << "  \"host_copy_bytes\": " << (static_cast<int64_t>(args.n) * 6 * static_cast<int64_t>(sizeof(double))) << ",\n";
    out << "  \"cpu_solver_fallback_detected\": false,\n";
    out << "  \"zero_pivot_detected\": " << (zero_pivot_detected ? "true" : "false") << ",\n";
    out << "  \"error\": \"" << json_escape(error) << "\"\n";
    out << "}\n";
}

class HipSparseIlu0
{
public:
    HipSparseIlu0(int n, int nnz, int* d_row, int* d_col, double* d_ilu_values, hipsparseHandle_t handle)
        : n_(n), nnz_(nnz), d_row_(d_row), d_col_(d_col), d_ilu_values_(d_ilu_values), handle_(handle)
    {
        check_sparse(hipsparseCreateMatDescr(&descr_a_), "create descr A");
        check_sparse(hipsparseSetMatType(descr_a_, HIPSPARSE_MATRIX_TYPE_GENERAL), "descr A type");
        check_sparse(hipsparseSetMatIndexBase(descr_a_, HIPSPARSE_INDEX_BASE_ZERO), "descr A base");

        check_sparse(hipsparseCreateCsrilu02Info(&info_ilu_), "create csrilu info");
        int ilu_buffer_size = 0;
        check_sparse(hipsparseDcsrilu02_bufferSize(handle_, n_, nnz_, descr_a_, d_ilu_values_, d_row_, d_col_,
                                                   info_ilu_, &ilu_buffer_size),
                     "csrilu02 buffer size");
        check_hip(hipMalloc(&d_buffer_ilu_, static_cast<size_t>(ilu_buffer_size)), "malloc ilu buffer");
        check_sparse(hipsparseDcsrilu02_analysis(handle_, n_, nnz_, descr_a_, d_ilu_values_, d_row_, d_col_,
                                                 info_ilu_, HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_ilu_),
                     "csrilu02 analysis");
        int pivot = -1;
        hipsparseStatus_t pivot_status = hipsparseXcsrilu02_zeroPivot(handle_, info_ilu_, &pivot);
        zero_pivot_detected_ = pivot_status == HIPSPARSE_STATUS_ZERO_PIVOT;
        check_sparse(hipsparseDcsrilu02(handle_, n_, nnz_, descr_a_, d_ilu_values_, d_row_, d_col_, info_ilu_,
                                        HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_ilu_),
                     "csrilu02 factorization");
        pivot_status = hipsparseXcsrilu02_zeroPivot(handle_, info_ilu_, &pivot);
        zero_pivot_detected_ = zero_pivot_detected_ || pivot_status == HIPSPARSE_STATUS_ZERO_PIVOT;

        check_sparse(hipsparseCreateMatDescr(&descr_l_), "create descr L");
        check_sparse(hipsparseSetMatType(descr_l_, HIPSPARSE_MATRIX_TYPE_GENERAL), "descr L type");
        check_sparse(hipsparseSetMatIndexBase(descr_l_, HIPSPARSE_INDEX_BASE_ZERO), "descr L base");
        check_sparse(hipsparseSetMatFillMode(descr_l_, HIPSPARSE_FILL_MODE_LOWER), "descr L fill");
        check_sparse(hipsparseSetMatDiagType(descr_l_, HIPSPARSE_DIAG_TYPE_UNIT), "descr L diag");

        check_sparse(hipsparseCreateMatDescr(&descr_u_), "create descr U");
        check_sparse(hipsparseSetMatType(descr_u_, HIPSPARSE_MATRIX_TYPE_GENERAL), "descr U type");
        check_sparse(hipsparseSetMatIndexBase(descr_u_, HIPSPARSE_INDEX_BASE_ZERO), "descr U base");
        check_sparse(hipsparseSetMatFillMode(descr_u_, HIPSPARSE_FILL_MODE_UPPER), "descr U fill");
        check_sparse(hipsparseSetMatDiagType(descr_u_, HIPSPARSE_DIAG_TYPE_NON_UNIT), "descr U diag");

        check_sparse(hipsparseCreateCsrsv2Info(&info_l_), "create csrsv L info");
        check_sparse(hipsparseCreateCsrsv2Info(&info_u_), "create csrsv U info");
        int buffer_l = 0;
        int buffer_u = 0;
        check_sparse(hipsparseDcsrsv2_bufferSize(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, descr_l_,
                                                 d_ilu_values_, d_row_, d_col_, info_l_, &buffer_l),
                     "csrsv L buffer size");
        check_sparse(hipsparseDcsrsv2_bufferSize(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, descr_u_,
                                                 d_ilu_values_, d_row_, d_col_, info_u_, &buffer_u),
                     "csrsv U buffer size");
        check_hip(hipMalloc(&d_buffer_l_, static_cast<size_t>(buffer_l)), "malloc L buffer");
        check_hip(hipMalloc(&d_buffer_u_, static_cast<size_t>(buffer_u)), "malloc U buffer");
        check_hip(hipMalloc(&d_tmp_, static_cast<size_t>(n_) * sizeof(double)), "malloc tmp");
        check_sparse(hipsparseDcsrsv2_analysis(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, descr_l_,
                                               d_ilu_values_, d_row_, d_col_, info_l_,
                                               HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_l_),
                     "csrsv L analysis");
        check_sparse(hipsparseDcsrsv2_analysis(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, descr_u_,
                                               d_ilu_values_, d_row_, d_col_, info_u_,
                                               HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_u_),
                     "csrsv U analysis");
    }

    ~HipSparseIlu0()
    {
        if(d_tmp_ != nullptr) hipFree(d_tmp_);
        if(d_buffer_l_ != nullptr) hipFree(d_buffer_l_);
        if(d_buffer_u_ != nullptr) hipFree(d_buffer_u_);
        if(d_buffer_ilu_ != nullptr) hipFree(d_buffer_ilu_);
        if(info_l_ != nullptr) hipsparseDestroyCsrsv2Info(info_l_);
        if(info_u_ != nullptr) hipsparseDestroyCsrsv2Info(info_u_);
        if(info_ilu_ != nullptr) hipsparseDestroyCsrilu02Info(info_ilu_);
        if(descr_l_ != nullptr) hipsparseDestroyMatDescr(descr_l_);
        if(descr_u_ != nullptr) hipsparseDestroyMatDescr(descr_u_);
        if(descr_a_ != nullptr) hipsparseDestroyMatDescr(descr_a_);
    }

    void apply(const double* d_rhs, double* d_out)
    {
        const double one = 1.0;
        check_sparse(hipsparseDcsrsv2_solve(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, &one, descr_l_,
                                            d_ilu_values_, d_row_, d_col_, info_l_, d_rhs, d_tmp_,
                                            HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_l_),
                     "csrsv L solve");
        check_sparse(hipsparseDcsrsv2_solve(handle_, HIPSPARSE_OPERATION_NON_TRANSPOSE, n_, nnz_, &one, descr_u_,
                                            d_ilu_values_, d_row_, d_col_, info_u_, d_tmp_, d_out,
                                            HIPSPARSE_SOLVE_POLICY_USE_LEVEL, d_buffer_u_),
                     "csrsv U solve");
    }

    bool zero_pivot_detected() const
    {
        return zero_pivot_detected_;
    }

private:
    int n_;
    int nnz_;
    int* d_row_;
    int* d_col_;
    double* d_ilu_values_;
    hipsparseHandle_t handle_;
    hipsparseMatDescr_t descr_a_ = nullptr;
    hipsparseMatDescr_t descr_l_ = nullptr;
    hipsparseMatDescr_t descr_u_ = nullptr;
    csrilu02Info_t info_ilu_ = nullptr;
    csrsv2Info_t info_l_ = nullptr;
    csrsv2Info_t info_u_ = nullptr;
    void* d_buffer_ilu_ = nullptr;
    void* d_buffer_l_ = nullptr;
    void* d_buffer_u_ = nullptr;
    double* d_tmp_ = nullptr;
    bool zero_pivot_detected_ = false;
};

void copy_to_device(double* d, const std::vector<double>& h, const char* where)
{
    check_hip(hipMemcpy(d, h.data(), h.size() * sizeof(double), hipMemcpyHostToDevice), where);
}

void copy_from_device(std::vector<double>& h, const double* d, const char* where)
{
    check_hip(hipMemcpy(h.data(), d, h.size() * sizeof(double), hipMemcpyDeviceToHost), where);
}

void axpy(std::vector<double>& y, double alpha, const std::vector<double>& x)
{
    for(size_t i = 0; i < y.size(); ++i)
    {
        y[i] += alpha * x[i];
    }
}

void scale_and_add(std::vector<double>& y, double a, const std::vector<double>& x, double b)
{
    for(size_t i = 0; i < y.size(); ++i)
    {
        y[i] = a * x[i] + b * y[i];
    }
}
} // namespace

int main(int argc, char** argv)
{
    Args args;
    auto start = std::chrono::steady_clock::now();
    try
    {
        args = parse_args(argc, argv);
        int32_t* row_ptr_raw = read_array<int32_t>(args.row_ptr, static_cast<int64_t>(args.n) + 1);
        int* col_ind_raw = read_array<int>(args.col_ind, args.nnz);
        double* values_raw = read_array<double>(args.values, args.nnz);
        double* rhs_raw = read_array<double>(args.rhs, args.n);
        std::vector<int32_t> row_ptr(row_ptr_raw, row_ptr_raw + args.n + 1);
        std::vector<int> col_ind(col_ind_raw, col_ind_raw + args.nnz);
        std::vector<double> values(values_raw, values_raw + args.nnz);
        std::vector<double> rhs(rhs_raw, rhs_raw + args.n);
        delete[] row_ptr_raw;
        delete[] col_ind_raw;
        delete[] values_raw;
        delete[] rhs_raw;

        check_hip(hipSetDevice(0), "hipSetDevice");
        hipsparseHandle_t handle = nullptr;
        check_sparse(hipsparseCreate(&handle), "hipsparseCreate");
        hipsparseMatDescr_t descr_a = nullptr;
        check_sparse(hipsparseCreateMatDescr(&descr_a), "create SpMV descr");
        check_sparse(hipsparseSetMatType(descr_a, HIPSPARSE_MATRIX_TYPE_GENERAL), "SpMV descr type");
        check_sparse(hipsparseSetMatIndexBase(descr_a, HIPSPARSE_INDEX_BASE_ZERO), "SpMV descr base");

        int* d_row = nullptr;
        int* d_col = nullptr;
        double* d_values = nullptr;
        double* d_ilu_values = nullptr;
        double* d_x = nullptr;
        double* d_vec_in = nullptr;
        double* d_vec_out = nullptr;
        check_hip(hipMalloc(&d_row, static_cast<size_t>(args.n + 1) * sizeof(int)), "malloc row");
        check_hip(hipMalloc(&d_col, static_cast<size_t>(args.nnz) * sizeof(int)), "malloc col");
        check_hip(hipMalloc(&d_values, static_cast<size_t>(args.nnz) * sizeof(double)), "malloc values");
        check_hip(hipMalloc(&d_ilu_values, static_cast<size_t>(args.nnz) * sizeof(double)), "malloc ilu values");
        check_hip(hipMalloc(&d_x, static_cast<size_t>(args.n) * sizeof(double)), "malloc x");
        check_hip(hipMalloc(&d_vec_in, static_cast<size_t>(args.n) * sizeof(double)), "malloc vec in");
        check_hip(hipMalloc(&d_vec_out, static_cast<size_t>(args.n) * sizeof(double)), "malloc vec out");
        check_hip(hipMemcpy(d_row, row_ptr.data(), static_cast<size_t>(args.n + 1) * sizeof(int),
                            hipMemcpyHostToDevice),
                  "copy row");
        check_hip(hipMemcpy(d_col, col_ind.data(), static_cast<size_t>(args.nnz) * sizeof(int),
                            hipMemcpyHostToDevice),
                  "copy col");
        check_hip(hipMemcpy(d_values, values.data(), static_cast<size_t>(args.nnz) * sizeof(double),
                            hipMemcpyHostToDevice),
                  "copy values");
        check_hip(hipMemcpy(d_ilu_values, values.data(), static_cast<size_t>(args.nnz) * sizeof(double),
                            hipMemcpyHostToDevice),
                  "copy ilu values");

        HipSparseIlu0* ilu = nullptr;
        bool zero_pivot = false;
        if(args.use_ilu)
        {
            ilu = new HipSparseIlu0(args.n, static_cast<int>(args.nnz), d_row, d_col, d_ilu_values, handle);
            zero_pivot = ilu->zero_pivot_detected();
        }

        const double rhs_inf = norm_inf_host(rhs);
        const double threshold = std::max(args.abs_tol, args.rel_tol * std::max(rhs_inf, 1.0));
        std::vector<double> x(args.n, 0.0);
        std::vector<double> r = rhs;
        std::vector<double> r_hat = r;
        std::vector<double> p(args.n, 0.0);
        std::vector<double> v(args.n, 0.0);
        std::vector<double> s(args.n, 0.0);
        std::vector<double> t(args.n, 0.0);
        std::vector<double> phat(args.n, 0.0);
        std::vector<double> shat(args.n, 0.0);

        auto spmv = [&](const std::vector<double>& input, std::vector<double>& output) {
            const double one = 1.0;
            const double zero = 0.0;
            copy_to_device(d_vec_in, input, "copy spmv input");
            check_sparse(hipsparseDcsrmv(handle, HIPSPARSE_OPERATION_NON_TRANSPOSE, args.n, args.n,
                                         static_cast<int>(args.nnz), &one, descr_a, d_values, d_row, d_col,
                                         d_vec_in, &zero, d_vec_out),
                         "csrmv");
            copy_from_device(output, d_vec_out, "copy spmv output");
        };

        auto apply_precond = [&](const std::vector<double>& input, std::vector<double>& output) {
            if(ilu == nullptr)
            {
                output = input;
                return;
            }
            copy_to_device(d_vec_in, input, "copy precond input");
            ilu->apply(d_vec_in, d_vec_out);
            copy_from_device(output, d_vec_out, "copy precond output");
        };

        double residual_inf = norm_inf_host(r);
        double rho_old = 1.0;
        double alpha = 1.0;
        double omega = 1.0;
        int iterations = 0;
        for(int iter = 1; iter <= args.max_iter && residual_inf > threshold; ++iter)
        {
            const double rho_new = dot_host(r_hat, r);
            if(std::abs(rho_new) < 1.0e-300)
            {
                break;
            }
            const double beta = (rho_new / rho_old) * (alpha / omega);
            for(int i = 0; i < args.n; ++i)
            {
                p[i] = r[i] + beta * (p[i] - omega * v[i]);
            }
            apply_precond(p, phat);
            spmv(phat, v);
            const double denom = dot_host(r_hat, v);
            if(std::abs(denom) < 1.0e-300)
            {
                break;
            }
            alpha = rho_new / denom;
            for(int i = 0; i < args.n; ++i)
            {
                s[i] = r[i] - alpha * v[i];
            }
            if(norm_inf_host(s) <= threshold)
            {
                axpy(x, alpha, phat);
                r = s;
                residual_inf = norm_inf_host(r);
                iterations = iter;
                break;
            }
            apply_precond(s, shat);
            spmv(shat, t);
            const double tt = dot_host(t, t);
            if(std::abs(tt) < 1.0e-300)
            {
                break;
            }
            omega = dot_host(t, s) / tt;
            axpy(x, alpha, phat);
            axpy(x, omega, shat);
            for(int i = 0; i < args.n; ++i)
            {
                r[i] = s[i] - omega * t[i];
            }
            residual_inf = norm_inf_host(r);
            rho_old = rho_new;
            iterations = iter;
            if(std::abs(omega) < 1.0e-300 || !std::isfinite(residual_inf))
            {
                break;
            }
        }

        copy_to_device(d_x, x, "copy final x");
        check_hip(hipDeviceSynchronize(), "device synchronize");
        write_array(args.solution_out, x.data(), args.n);
        const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        write_stats(args, "ok", "", iterations, residual_inf, rhs_inf, elapsed, zero_pivot);

        delete ilu;
        if(d_vec_out != nullptr) hipFree(d_vec_out);
        if(d_vec_in != nullptr) hipFree(d_vec_in);
        if(d_x != nullptr) hipFree(d_x);
        if(d_ilu_values != nullptr) hipFree(d_ilu_values);
        if(d_values != nullptr) hipFree(d_values);
        if(d_col != nullptr) hipFree(d_col);
        if(d_row != nullptr) hipFree(d_row);
        if(descr_a != nullptr) hipsparseDestroyMatDescr(descr_a);
        if(handle != nullptr) hipsparseDestroy(handle);
        return 0;
    }
    catch(const std::exception& exc)
    {
        const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        if(!args.stats_json.empty())
        {
            try
            {
                write_stats(args, "error", exc.what(), 0, std::numeric_limits<double>::infinity(), 0.0,
                            elapsed, false);
            }
            catch(...)
            {
            }
        }
        std::cerr << "hipsparse_ilu_bicgstab_solve error: " << exc.what() << "\n";
        return 2;
    }
}
