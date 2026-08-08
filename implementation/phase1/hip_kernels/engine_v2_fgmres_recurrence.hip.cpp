#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::array<char, 8> kMagic = {'E', 'V', '2', 'F', 'G', 'R', '0', '1'};
constexpr std::array<char, 8> kCheckpointMagic = {
    'E', 'V', '2', 'F', 'G', 'C', 'P', '1'};
#ifndef ENGINE_V2_FGMRES_MAXIMUM_FIXTURE_DIMENSION
#define ENGINE_V2_FGMRES_MAXIMUM_FIXTURE_DIMENSION 4092
#endif
constexpr int kMaximumFixtureDimension =
    ENGINE_V2_FGMRES_MAXIMUM_FIXTURE_DIMENSION;
constexpr int kMaximumRestart = 32;
constexpr int kMaximumIterations = 128;
constexpr int kMaximumRestartRecords = 129;
constexpr int kThreadsPerCase = 64;
constexpr int kOperatorBlocksPerCase = 4;

enum TerminalCode : int {
  kUnset = 0,
  kInitialResidualSatisfied = 1,
  kConvergedScaledResidual = 2,
  kMaxIterations = 3,
  kArnoldiBreakdown = 4,
  kRestarted = 5,
};

struct CaseConfig {
  std::uint64_t max_iterations;
  std::uint64_t restart_length;
  double relative_tolerance;
  double absolute_tolerance;
  double breakdown_tolerance;
};

struct ResumeConfig {
  int enabled;
  int iteration_count;
  int matvec_count;
  int next_restart_index;
  double convergence_threshold;
};

struct CaseOutput {
  int status_code;
  int terminal_code;
  int converged;
  int iteration_count;
  int matvec_count;
  int restart_count;
  int resumed_from_iteration;
  int restart_index_base;
  int history_count;
  int completed_iteration_replay_count;
  double convergence_threshold;
  double scaled_l2_history[kMaximumIterations + 1];
  double scaled_linf_history[kMaximumIterations + 1];
  int restart_start[kMaximumRestartRecords];
  int restart_end[kMaximumRestartRecords];
  int restart_disposition[kMaximumRestartRecords];
};

struct MultiBlockState {
  CaseOutput output;
  int terminal_code;
  int total_iterations;
  int history_iteration_base;
  int cycle_start_iteration;
  int cycle_end_iteration;
  int cycle_started;
  int radius_invalid;
  int back_substitution_ok;
  double beta;
  double next_norm;
  double observed_l2;
  double observed_linf;
  double coefficient;
  double hessenberg[(kMaximumRestart + 1) * kMaximumRestart];
  double cosines[kMaximumRestart];
  double sines[kMaximumRestart];
  double projected_rhs[kMaximumRestart + 1];
  double coefficients[kMaximumRestart];
};

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
  }
}

template <typename T>
void read_scalar(std::ifstream& input, T& value) {
  input.read(reinterpret_cast<char*>(&value), static_cast<std::streamsize>(sizeof(T)));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
}

template <typename T>
void read_vector(std::ifstream& input, std::vector<T>& values) {
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
}

template <typename T>
T* allocate_and_copy(const std::vector<T>& host, hipStream_t stream) {
  T* device = nullptr;
  check_hip(hipMalloc(&device, host.size() * sizeof(T)), "hipMalloc");
  check_hip(hipMemcpyAsync(device, host.data(), host.size() * sizeof(T),
                           hipMemcpyHostToDevice, stream),
            "hipMemcpyAsync_h2d");
  return device;
}

__device__ double block_sum(double value, double* scratch) {
  const int thread = static_cast<int>(threadIdx.x);
  scratch[thread] = value;
  __syncthreads();
  for (int stride = kThreadsPerCase / 2; stride > 0; stride /= 2) {
    if (thread < stride) {
      scratch[thread] += scratch[thread + stride];
    }
    __syncthreads();
  }
  return scratch[0];
}

__device__ double block_max(double value, double* scratch) {
  const int thread = static_cast<int>(threadIdx.x);
  scratch[thread] = value;
  __syncthreads();
  for (int stride = kThreadsPerCase / 2; stride > 0; stride /= 2) {
    if (thread < stride) {
      scratch[thread] = fmax(scratch[thread], scratch[thread + stride]);
    }
    __syncthreads();
  }
  return scratch[0];
}

__device__ double block_l2(const double* values, int count, double* scratch) {
  double local = 0.0;
  for (int index = static_cast<int>(threadIdx.x); index < count;
       index += kThreadsPerCase) {
    local += values[index] * values[index];
  }
  return sqrt(block_sum(local, scratch));
}

__device__ double block_linf(const double* values, int count, double* scratch) {
  double local = 0.0;
  for (int index = static_cast<int>(threadIdx.x); index < count;
       index += kThreadsPerCase) {
    local = fmax(local, fabs(values[index]));
  }
  return block_max(local, scratch);
}

__device__ double block_dot(const double* left, const double* right, int count,
                            double* scratch) {
  double local = 0.0;
  for (int index = static_cast<int>(threadIdx.x); index < count;
       index += kThreadsPerCase) {
    local += left[index] * right[index];
  }
  return block_sum(local, scratch);
}

__device__ void block_csr_matvec(int n, const std::int64_t* row_ptr,
                                 const std::int32_t* columns,
                                 const double* values, const double* vector,
                                 double* result) {
  for (int row = static_cast<int>(threadIdx.x); row < n;
       row += kThreadsPerCase) {
    double sum = 0.0;
    for (std::int64_t position = row_ptr[row]; position < row_ptr[row + 1];
         ++position) {
      sum += values[position] * vector[columns[position]];
    }
    result[row] = sum;
  }
  __syncthreads();
}

__device__ void block_observe_residual(
    int n, const std::int64_t* row_ptr, const std::int32_t* columns,
    const double* values, const double* right_hand_side, const double* scale,
    const double* solution, double* internal, double* recurrence_residual) {
  block_csr_matvec(n, row_ptr, columns, values, solution, internal);
  for (int index = static_cast<int>(threadIdx.x); index < n;
       index += kThreadsPerCase) {
    recurrence_residual[index] =
        (right_hand_side[index] - internal[index]) / scale[index];
  }
  __syncthreads();
}

__device__ void block_left_scaled_matvec(
    int n, const std::int64_t* row_ptr, const std::int32_t* columns,
    const double* values, const double* scale, const double* vector,
    double* result) {
  block_csr_matvec(n, row_ptr, columns, values, vector, result);
  for (int index = static_cast<int>(threadIdx.x); index < n;
       index += kThreadsPerCase) {
    result[index] /= scale[index];
  }
  __syncthreads();
}

__global__ void fgmres_recurrence_kernel(
    int n, int case_count, const std::int64_t* row_ptr,
    const std::int32_t* columns, const double* values,
    const double* right_hand_side, const double* scale,
    const double* initial_solution, const double* inverse_diagonal,
    const CaseConfig* configurations, const ResumeConfig* resumes,
    const double* resume_vectors, double* workspace,
    std::uint64_t workspace_stride, CaseOutput* outputs,
    double* output_solutions) {
  const int case_index = static_cast<int>(blockIdx.x);
  const int thread = static_cast<int>(threadIdx.x);
  if (case_index >= case_count) {
    return;
  }
  CaseOutput& output = outputs[case_index];
  const CaseConfig config = configurations[case_index];
  const ResumeConfig resume = resumes[case_index];
  double* const case_workspace =
      workspace + static_cast<std::uint64_t>(case_index) * workspace_stride;
  double* const current = case_workspace;
  double* const recurrence_residual = current + n;
  double* const cycle_solution = recurrence_residual + n;
  double* const candidate = cycle_solution + n;
  double* const work = candidate + n;
  double* const internal = work + n;
  double* const basis_v = internal + n;
  double* const basis_z = basis_v + (kMaximumRestart + 1) * n;
  const double* const resume_solution =
      resume_vectors + static_cast<std::uint64_t>(case_index) * 2 * n;
  const double* const resume_residual = resume_solution + n;
  double* const output_solution =
      output_solutions + static_cast<std::uint64_t>(case_index) * n;
  __shared__ double hessenberg[(kMaximumRestart + 1) * kMaximumRestart];
  __shared__ double cosines[kMaximumRestart];
  __shared__ double sines[kMaximumRestart];
  __shared__ double projected_rhs[kMaximumRestart + 1];
  __shared__ double coefficients[kMaximumRestart];
  __shared__ double reduction[kThreadsPerCase];
  __shared__ double beta;
  __shared__ double next_norm;
  __shared__ double observed_l2;
  __shared__ double observed_linf;
  __shared__ double coefficient;
  __shared__ int validation_ok;
  __shared__ int finished;
  __shared__ int total_iterations;
  __shared__ int history_iteration_base;
  __shared__ int terminal_code;
  __shared__ int cycle_start_iteration;
  __shared__ int cycle_end_iteration;
  __shared__ int capacity;
  __shared__ int radius_invalid;
  __shared__ int back_substitution_ok;

  if (thread == 0) {
    output.status_code = 0;
    output.terminal_code = kUnset;
    output.converged = 0;
    output.iteration_count = 0;
    output.matvec_count = 0;
    output.restart_count = 0;
    output.resumed_from_iteration = 0;
    output.restart_index_base = 0;
    output.history_count = 0;
    output.completed_iteration_replay_count = 0;
    total_iterations = 0;
    history_iteration_base = 0;
    terminal_code = kUnset;
    finished = 0;
    validation_ok =
        blockDim.x == kThreadsPerCase && n > 0 &&
        n <= kMaximumFixtureDimension &&
        config.max_iterations > 0 &&
        config.max_iterations <= kMaximumIterations &&
        config.restart_length > 0 &&
        config.restart_length <= static_cast<std::uint64_t>(n) &&
        config.restart_length <= kMaximumRestart &&
        (resume.enabled == 0 ||
         (resume.iteration_count > 0 &&
          resume.iteration_count < static_cast<int>(config.max_iterations) &&
          resume.matvec_count == 1 + 2 * resume.iteration_count &&
          resume.next_restart_index > 0 &&
          resume.iteration_count % static_cast<int>(config.restart_length) == 0 &&
          isfinite(resume.convergence_threshold) &&
          resume.convergence_threshold >= 0.0));
    if (!validation_ok) {
      output.status_code = 1;
    }
  }
  __syncthreads();
  if (!validation_ok) {
    return;
  }

  if (resume.enabled != 0) {
    if (thread == 0) {
      total_iterations = resume.iteration_count;
      history_iteration_base = resume.iteration_count;
      output.matvec_count = resume.matvec_count;
      output.resumed_from_iteration = resume.iteration_count;
      output.restart_index_base = resume.next_restart_index;
      output.convergence_threshold = resume.convergence_threshold;
    }
    for (int index = thread; index < n; index += kThreadsPerCase) {
      current[index] = resume_solution[index];
      recurrence_residual[index] = resume_residual[index];
    }
    __syncthreads();
    const double initial_l2 = block_l2(recurrence_residual, n, reduction);
    const double initial_linf = block_linf(recurrence_residual, n, reduction);
    if (thread == 0) {
      output.scaled_l2_history[0] = initial_l2;
      output.scaled_linf_history[0] = initial_linf;
      output.history_count = 1;
      if (initial_l2 <= output.convergence_threshold) {
        output.status_code = 2;
        finished = 1;
      }
    }
    __syncthreads();
  } else {
    for (int index = thread; index < n; index += kThreadsPerCase) {
      current[index] = initial_solution[index];
    }
    __syncthreads();
    block_observe_residual(n, row_ptr, columns, values, right_hand_side, scale,
                           current, internal, recurrence_residual);
    const double initial_l2 = block_l2(recurrence_residual, n, reduction);
    const double initial_linf = block_linf(recurrence_residual, n, reduction);
    if (thread == 0) {
      output.matvec_count = 1;
      output.scaled_l2_history[0] = initial_l2;
      output.scaled_linf_history[0] = initial_linf;
      output.history_count = 1;
      output.convergence_threshold = fmax(
          config.absolute_tolerance, config.relative_tolerance * initial_l2);
      if (initial_l2 <= output.convergence_threshold) {
        output.terminal_code = kInitialResidualSatisfied;
        output.converged = 1;
        output.restart_count = 1;
        output.restart_start[0] = 0;
        output.restart_end[0] = 0;
        output.restart_disposition[0] = kInitialResidualSatisfied;
        terminal_code = kInitialResidualSatisfied;
        finished = 1;
      }
    }
    __syncthreads();
  }

  if (finished) {
    for (int index = thread; index < n; index += kThreadsPerCase) {
      output_solution[index] = current[index];
    }
    return;
  }

  while (terminal_code == kUnset) {
    if (thread == 0) {
      cycle_start_iteration = total_iterations;
    }
    for (int index = thread; index < n; index += kThreadsPerCase) {
      cycle_solution[index] = current[index];
    }
    __syncthreads();
    const double cycle_beta = block_l2(recurrence_residual, n, reduction);
    if (thread == 0) {
      beta = cycle_beta;
      if (beta <= config.breakdown_tolerance) {
        terminal_code = kArnoldiBreakdown;
        const int record = output.restart_count++;
        output.restart_start[record] = cycle_start_iteration;
        output.restart_end[record] = cycle_start_iteration;
        output.restart_disposition[record] = terminal_code;
      } else {
        const int remaining =
            static_cast<int>(config.max_iterations) - total_iterations;
        capacity =
            min(static_cast<int>(config.restart_length), remaining);
      }
    }
    __syncthreads();
    if (terminal_code != kUnset) {
      break;
    }

    for (int index = thread; index < n; index += kThreadsPerCase) {
      basis_v[index] = recurrence_residual[index] / beta;
    }
    for (int row = thread; row <= capacity; row += kThreadsPerCase) {
      projected_rhs[row] = 0.0;
    }
    for (int flat = thread; flat < (capacity + 1) * capacity;
         flat += kThreadsPerCase) {
      const int row = flat / capacity;
      const int column = flat % capacity;
      hessenberg[row * kMaximumRestart + column] = 0.0;
    }
    for (int index = thread; index < capacity; index += kThreadsPerCase) {
      cosines[index] = 0.0;
      sines[index] = 0.0;
    }
    if (thread == 0) {
      projected_rhs[0] = beta;
      cycle_end_iteration = cycle_start_iteration;
    }
    __syncthreads();

    for (int inner = 0; inner < capacity; ++inner) {
      for (int index = thread; index < n; index += kThreadsPerCase) {
        basis_z[inner * n + index] =
            inverse_diagonal[index] *
            basis_v[inner * n + index];
      }
      __syncthreads();
      block_left_scaled_matvec(n, row_ptr, columns, values, scale,
                               &basis_z[inner * n], work);
      if (thread == 0) {
        output.matvec_count += 1;
      }
      __syncthreads();
      for (int pass = 0; pass < 2; ++pass) {
        for (int basis = 0; basis <= inner; ++basis) {
          const double projection = block_dot(
              &basis_v[basis * n], work, n, reduction);
          if (thread == 0) {
            coefficient = projection;
            hessenberg[basis * kMaximumRestart + inner] += coefficient;
          }
          __syncthreads();
          for (int index = thread; index < n; index += kThreadsPerCase) {
            work[index] -=
                coefficient * basis_v[basis * n + index];
          }
          __syncthreads();
        }
      }
      const double arnoldi_norm = block_l2(work, n, reduction);
      if (thread == 0) {
        next_norm = arnoldi_norm;
        hessenberg[(inner + 1) * kMaximumRestart + inner] = next_norm;
      }
      __syncthreads();
      if (next_norm > config.breakdown_tolerance) {
        for (int index = thread; index < n; index += kThreadsPerCase) {
          basis_v[(inner + 1) * n + index] =
              work[index] / next_norm;
        }
      }
      __syncthreads();
      if (thread == 0) {
        for (int prior = 0; prior < inner; ++prior) {
          const double upper = hessenberg[prior * kMaximumRestart + inner];
          const double lower =
              hessenberg[(prior + 1) * kMaximumRestart + inner];
          hessenberg[prior * kMaximumRestart + inner] =
              cosines[prior] * upper + sines[prior] * lower;
          hessenberg[(prior + 1) * kMaximumRestart + inner] =
              -sines[prior] * upper + cosines[prior] * lower;
        }
        const double diagonal = hessenberg[inner * kMaximumRestart + inner];
        const double subdiagonal =
            hessenberg[(inner + 1) * kMaximumRestart + inner];
        const double radius = hypot(diagonal, subdiagonal);
        radius_invalid =
            !isfinite(radius) || radius <= config.breakdown_tolerance;
        if (!radius_invalid) {
          cosines[inner] = diagonal / radius;
          sines[inner] = subdiagonal / radius;
          hessenberg[inner * kMaximumRestart + inner] = radius;
          hessenberg[(inner + 1) * kMaximumRestart + inner] = 0.0;
          const double projected_value = projected_rhs[inner];
          projected_rhs[inner] = cosines[inner] * projected_value;
          projected_rhs[inner + 1] = -sines[inner] * projected_value;
        }
      }
      __syncthreads();
      if (radius_invalid) {
        if (thread == 0) {
          ++total_iterations;
        }
        __syncthreads();
        block_observe_residual(n, row_ptr, columns, values, right_hand_side,
                               scale, current, internal, recurrence_residual);
        const double l2 = block_l2(recurrence_residual, n, reduction);
        const double linf = block_linf(recurrence_residual, n, reduction);
        if (thread == 0) {
          observed_l2 = l2;
          observed_linf = linf;
          output.matvec_count += 1;
          const int history_index =
              total_iterations - history_iteration_base;
          output.scaled_l2_history[history_index] = observed_l2;
          output.scaled_linf_history[history_index] = observed_linf;
          output.history_count = history_index + 1;
          cycle_end_iteration = total_iterations;
          terminal_code = kArnoldiBreakdown;
        }
        __syncthreads();
        break;
      }

      if (thread == 0) {
        back_substitution_ok = 1;
        for (int row = inner; row >= 0; --row) {
          const double pivot = hessenberg[row * kMaximumRestart + row];
          if (fabs(pivot) <= config.breakdown_tolerance) {
            back_substitution_ok = 0;
            break;
          }
          double tail = 0.0;
          for (int column = row + 1; column <= inner; ++column) {
            tail += hessenberg[row * kMaximumRestart + column] *
                    coefficients[column];
          }
          coefficients[row] = (projected_rhs[row] - tail) / pivot;
        }
        if (!back_substitution_ok) {
          terminal_code = kArnoldiBreakdown;
        }
      }
      __syncthreads();
      for (int row = thread; row < n; row += kThreadsPerCase) {
        if (!back_substitution_ok) {
          candidate[row] = current[row];
        } else {
          double value = cycle_solution[row];
          for (int column = 0; column <= inner; ++column) {
            value += basis_z[column * n + row] *
                     coefficients[column];
          }
          candidate[row] = value;
        }
      }
      __syncthreads();
      if (thread == 0) {
        ++total_iterations;
      }
      __syncthreads();
      block_observe_residual(n, row_ptr, columns, values, right_hand_side,
                             scale, candidate, internal, recurrence_residual);
      const double l2 = block_l2(recurrence_residual, n, reduction);
      const double linf = block_linf(recurrence_residual, n, reduction);
      for (int index = thread; index < n; index += kThreadsPerCase) {
        current[index] = candidate[index];
      }
      __syncthreads();
      if (thread == 0) {
        observed_l2 = l2;
        observed_linf = linf;
        output.matvec_count += 1;
        const int history_index = total_iterations - history_iteration_base;
        output.scaled_l2_history[history_index] = observed_l2;
        output.scaled_linf_history[history_index] = observed_linf;
        output.history_count = history_index + 1;
        cycle_end_iteration = total_iterations;
        if (observed_l2 <= output.convergence_threshold) {
          terminal_code = kConvergedScaledResidual;
        } else if (terminal_code == kArnoldiBreakdown ||
                   next_norm <= config.breakdown_tolerance) {
          terminal_code = kArnoldiBreakdown;
        } else if (total_iterations ==
                   static_cast<int>(config.max_iterations)) {
          terminal_code = kMaxIterations;
        }
      }
      __syncthreads();
      if (terminal_code != kUnset) {
        break;
      }
    }
    if (thread == 0) {
      const int record = output.restart_count++;
      output.restart_start[record] = cycle_start_iteration;
      output.restart_end[record] = cycle_end_iteration;
      output.restart_disposition[record] =
          terminal_code == kUnset ? kRestarted : terminal_code;
    }
    __syncthreads();
  }

  if (thread == 0) {
    output.terminal_code = terminal_code;
    output.converged = terminal_code == kConvergedScaledResidual ? 1 : 0;
    output.iteration_count = total_iterations;
  }
  for (int index = thread; index < n; index += kThreadsPerCase) {
    output_solution[index] = current[index];
  }
}

__device__ bool multi_block_active(const MultiBlockState* state,
                                   int expected_iteration) {
  return state->terminal_code == kUnset &&
         state->total_iterations == expected_iteration;
}

__global__ void multi_block_initialize_state(MultiBlockState* state,
                                             CaseConfig config,
                                             ResumeConfig resume) {
  if (blockIdx.x != 0 || threadIdx.x != 0) {
    return;
  }
  state->output.status_code = 0;
  state->output.terminal_code = kUnset;
  state->output.converged = 0;
  state->output.iteration_count = resume.enabled ? resume.iteration_count : 0;
  state->output.matvec_count = resume.enabled ? resume.matvec_count : 0;
  state->output.restart_count = 0;
  state->output.resumed_from_iteration =
      resume.enabled ? resume.iteration_count : 0;
  state->output.restart_index_base =
      resume.enabled ? resume.next_restart_index : 0;
  state->output.history_count = 0;
  state->output.completed_iteration_replay_count = 0;
  state->output.convergence_threshold =
      resume.enabled ? resume.convergence_threshold : 0.0;
  state->terminal_code = kUnset;
  state->total_iterations = resume.enabled ? resume.iteration_count : 0;
  state->history_iteration_base =
      resume.enabled ? resume.iteration_count : 0;
  state->cycle_start_iteration = state->total_iterations;
  state->cycle_end_iteration = state->total_iterations;
  state->cycle_started = 0;
  state->radius_invalid = 0;
  state->back_substitution_ok = 1;
  state->beta = 0.0;
  state->next_norm = 0.0;
  state->observed_l2 = 0.0;
  state->observed_linf = 0.0;
  state->coefficient = 0.0;
  (void)config;
}

__global__ void multi_block_initialize_vectors(
    int n, int resume_enabled, const double* initial_solution,
    const double* resume_solution, const double* resume_residual,
    double* current, double* recurrence_residual) {
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    current[index] =
        resume_enabled ? resume_solution[index] : initial_solution[index];
    recurrence_residual[index] =
        resume_enabled ? resume_residual[index] : 0.0;
  }
}

__global__ void multi_block_spmv(
    int n, int expected_iteration, int increment_matvec,
    const std::int64_t* row_ptr, const std::int32_t* columns,
    const double* values, const double* vector, double* result,
    MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  if (blockIdx.x == 0 && threadIdx.x == 0 && increment_matvec != 0) {
    state->output.matvec_count += 1;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int row = global_thread; row < n; row += stride) {
    double sum = 0.0;
    for (std::int64_t position = row_ptr[row]; position < row_ptr[row + 1];
         ++position) {
      sum += values[position] * vector[columns[position]];
    }
    result[row] = sum;
  }
}

__global__ void multi_block_scaled_spmv(
    int n, int expected_iteration, const std::int64_t* row_ptr,
    const std::int32_t* columns, const double* values, const double* scale,
    const double* vector, double* result, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  if (blockIdx.x == 0 && threadIdx.x == 0) {
    state->output.matvec_count += 1;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int row = global_thread; row < n; row += stride) {
    double sum = 0.0;
    for (std::int64_t position = row_ptr[row]; position < row_ptr[row + 1];
         ++position) {
      sum += values[position] * vector[columns[position]];
    }
    result[row] = sum / scale[row];
  }
}

__global__ void multi_block_residual(
    int n, int expected_iteration, const double* right_hand_side,
    const double* scale, const double* internal,
    double* recurrence_residual, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    recurrence_residual[index] =
        (right_hand_side[index] - internal[index]) / scale[index];
  }
}

__global__ void multi_block_norm_partials(
    int n, int expected_iteration, const double* vector, double* partials,
    MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  __shared__ double sum_scratch[kThreadsPerCase];
  __shared__ double max_scratch[kThreadsPerCase];
  double local_sum = 0.0;
  double local_max = 0.0;
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    const double value = vector[index];
    local_sum += value * value;
    local_max = fmax(local_max, fabs(value));
  }
  const double block_squared = block_sum(local_sum, sum_scratch);
  const double block_infinity = block_max(local_max, max_scratch);
  if (threadIdx.x == 0) {
    partials[blockIdx.x] = block_squared;
    partials[kOperatorBlocksPerCase + blockIdx.x] = block_infinity;
  }
}

__global__ void multi_block_norm_finalize(
    int expected_iteration, int target, int inner, const double* partials,
    MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  __shared__ double sum_scratch[kThreadsPerCase];
  __shared__ double max_scratch[kThreadsPerCase];
  const int thread = static_cast<int>(threadIdx.x);
  const double local_sum = thread < kOperatorBlocksPerCase ? partials[thread] : 0.0;
  const double local_max = thread < kOperatorBlocksPerCase
                               ? partials[kOperatorBlocksPerCase + thread]
                               : 0.0;
  const double norm = sqrt(block_sum(local_sum, sum_scratch));
  const double infinity = block_max(local_max, max_scratch);
  if (thread == 0) {
    if (target == 0) {
      state->observed_l2 = norm;
      state->observed_linf = infinity;
    } else {
      state->next_norm = norm;
      state->hessenberg[(inner + 1) * kMaximumRestart + inner] = norm;
    }
  }
}

__global__ void multi_block_finalize_initial(int resume_enabled,
                                             CaseConfig config,
                                             MultiBlockState* state) {
  if (blockIdx.x != 0 || threadIdx.x != 0 ||
      state->terminal_code != kUnset) {
    return;
  }
  if (!resume_enabled) {
    state->output.convergence_threshold =
        fmax(config.absolute_tolerance,
             config.relative_tolerance * state->observed_l2);
  }
  state->output.scaled_l2_history[0] = state->observed_l2;
  state->output.scaled_linf_history[0] = state->observed_linf;
  state->output.history_count = 1;
  if (state->observed_l2 <= state->output.convergence_threshold) {
    state->terminal_code = kInitialResidualSatisfied;
    state->output.terminal_code = kInitialResidualSatisfied;
    state->output.converged = 1;
    state->output.restart_count = 1;
    state->output.restart_start[0] = state->total_iterations;
    state->output.restart_end[0] = state->total_iterations;
    state->output.restart_disposition[0] = kInitialResidualSatisfied;
  }
}

__global__ void multi_block_begin_cycle(int expected_iteration,
                                        int capacity, CaseConfig config,
                                        MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int thread = static_cast<int>(threadIdx.x);
  if (thread == 0) {
    state->cycle_start_iteration = expected_iteration;
    state->cycle_end_iteration = expected_iteration;
    state->cycle_started = 1;
    state->beta = state->observed_l2;
    if (state->beta <= config.breakdown_tolerance) {
      state->terminal_code = kArnoldiBreakdown;
      state->output.terminal_code = kArnoldiBreakdown;
      state->output.converged = 0;
      state->output.iteration_count = state->total_iterations;
    }
  }
  __syncthreads();
  if (state->terminal_code != kUnset) {
    return;
  }
  for (int row = thread; row <= capacity; row += kThreadsPerCase) {
    state->projected_rhs[row] = 0.0;
  }
  for (int flat = thread; flat < (capacity + 1) * capacity;
       flat += kThreadsPerCase) {
    const int row = flat / capacity;
    const int column = flat % capacity;
    state->hessenberg[row * kMaximumRestart + column] = 0.0;
  }
  for (int index = thread; index < capacity; index += kThreadsPerCase) {
    state->cosines[index] = 0.0;
    state->sines[index] = 0.0;
  }
  __syncthreads();
  if (thread == 0) {
    state->projected_rhs[0] = state->beta;
  }
}

__global__ void multi_block_begin_cycle_vectors(
    int n, int expected_iteration, const double* current,
    const double* recurrence_residual, double* cycle_solution,
    double* basis_v, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration) ||
      state->cycle_started == 0) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    cycle_solution[index] = current[index];
    basis_v[index] = recurrence_residual[index] / state->beta;
  }
}

__global__ void multi_block_apply_preconditioner(
    int n, int expected_iteration, int inner, const double* inverse_diagonal,
    const double* basis_v, double* basis_z, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    basis_z[inner * n + index] =
        inverse_diagonal[index] * basis_v[inner * n + index];
  }
}

__global__ void multi_block_dot_partials(
    int n, int expected_iteration, const double* left, const double* right,
    double* partials, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  __shared__ double scratch[kThreadsPerCase];
  double local = 0.0;
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    local += left[index] * right[index];
  }
  const double block_value = block_sum(local, scratch);
  if (threadIdx.x == 0) {
    partials[blockIdx.x] = block_value;
  }
}

__global__ void multi_block_dot_finalize(int expected_iteration, int basis,
                                         int inner, const double* partials,
                                         MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  __shared__ double scratch[kThreadsPerCase];
  const int thread = static_cast<int>(threadIdx.x);
  const double local = thread < kOperatorBlocksPerCase ? partials[thread] : 0.0;
  const double value = block_sum(local, scratch);
  if (thread == 0) {
    state->coefficient = value;
    state->hessenberg[basis * kMaximumRestart + inner] += value;
  }
}

__global__ void multi_block_axpy_work(int n, int expected_iteration,
                                      int basis, const double* basis_v,
                                      double* work, MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    work[index] -= state->coefficient * basis_v[basis * n + index];
  }
}

__global__ void multi_block_normalize_next(int n, int expected_iteration,
                                           int inner, CaseConfig config,
                                           const double* work, double* basis_v,
                                           MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  if (state->next_norm <= config.breakdown_tolerance) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    basis_v[(inner + 1) * n + index] = work[index] / state->next_norm;
  }
}

__global__ void multi_block_givens_back_substitution(
    int expected_iteration, int inner, CaseConfig config,
    MultiBlockState* state) {
  if (blockIdx.x != 0 || threadIdx.x != 0 ||
      !multi_block_active(state, expected_iteration)) {
    return;
  }
  for (int prior = 0; prior < inner; ++prior) {
    const double upper =
        state->hessenberg[prior * kMaximumRestart + inner];
    const double lower =
        state->hessenberg[(prior + 1) * kMaximumRestart + inner];
    state->hessenberg[prior * kMaximumRestart + inner] =
        state->cosines[prior] * upper + state->sines[prior] * lower;
    state->hessenberg[(prior + 1) * kMaximumRestart + inner] =
        -state->sines[prior] * upper + state->cosines[prior] * lower;
  }
  const double diagonal =
      state->hessenberg[inner * kMaximumRestart + inner];
  const double subdiagonal =
      state->hessenberg[(inner + 1) * kMaximumRestart + inner];
  const double radius = hypot(diagonal, subdiagonal);
  state->radius_invalid =
      !isfinite(radius) || radius <= config.breakdown_tolerance;
  state->back_substitution_ok = 0;
  if (state->radius_invalid) {
    return;
  }
  state->cosines[inner] = diagonal / radius;
  state->sines[inner] = subdiagonal / radius;
  state->hessenberg[inner * kMaximumRestart + inner] = radius;
  state->hessenberg[(inner + 1) * kMaximumRestart + inner] = 0.0;
  const double projected_value = state->projected_rhs[inner];
  state->projected_rhs[inner] = state->cosines[inner] * projected_value;
  state->projected_rhs[inner + 1] =
      -state->sines[inner] * projected_value;
  state->back_substitution_ok = 1;
  for (int row = inner; row >= 0; --row) {
    const double pivot = state->hessenberg[row * kMaximumRestart + row];
    if (fabs(pivot) <= config.breakdown_tolerance) {
      state->back_substitution_ok = 0;
      break;
    }
    double tail = 0.0;
    for (int column = row + 1; column <= inner; ++column) {
      tail += state->hessenberg[row * kMaximumRestart + column] *
              state->coefficients[column];
    }
    state->coefficients[row] =
        (state->projected_rhs[row] - tail) / pivot;
  }
}

__global__ void multi_block_build_candidate(
    int n, int expected_iteration, int inner, const double* current,
    const double* cycle_solution, const double* basis_z, double* candidate,
    MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int row = global_thread; row < n; row += stride) {
    if (state->radius_invalid || !state->back_substitution_ok) {
      candidate[row] = current[row];
    } else {
      double value = cycle_solution[row];
      for (int column = 0; column <= inner; ++column) {
        value += basis_z[column * n + row] * state->coefficients[column];
      }
      candidate[row] = value;
    }
  }
}

__global__ void multi_block_increment_iteration(int expected_iteration,
                                                MultiBlockState* state) {
  if (blockIdx.x == 0 && threadIdx.x == 0 &&
      multi_block_active(state, expected_iteration)) {
    state->total_iterations += 1;
  }
}

__global__ void multi_block_update_current(int n, int expected_iteration,
                                           const double* candidate,
                                           double* current,
                                           MultiBlockState* state) {
  if (!multi_block_active(state, expected_iteration)) {
    return;
  }
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    current[index] = candidate[index];
  }
}

__global__ void multi_block_finalize_iteration(int expected_iteration,
                                               CaseConfig config,
                                               MultiBlockState* state) {
  if (blockIdx.x != 0 || threadIdx.x != 0 ||
      !multi_block_active(state, expected_iteration)) {
    return;
  }
  const int history_index =
      state->total_iterations - state->history_iteration_base;
  state->output.scaled_l2_history[history_index] = state->observed_l2;
  state->output.scaled_linf_history[history_index] = state->observed_linf;
  state->output.history_count = history_index + 1;
  state->cycle_end_iteration = state->total_iterations;
  state->output.iteration_count = state->total_iterations;
  if (state->observed_l2 <= state->output.convergence_threshold) {
    state->terminal_code = kConvergedScaledResidual;
  } else if (state->radius_invalid || !state->back_substitution_ok ||
             state->next_norm <= config.breakdown_tolerance) {
    state->terminal_code = kArnoldiBreakdown;
  } else if (state->total_iterations ==
             static_cast<int>(config.max_iterations)) {
    state->terminal_code = kMaxIterations;
  }
  if (state->terminal_code != kUnset) {
    state->output.terminal_code = state->terminal_code;
    state->output.converged =
        state->terminal_code == kConvergedScaledResidual ? 1 : 0;
  }
}

__global__ void multi_block_finish_cycle(MultiBlockState* state) {
  if (blockIdx.x != 0 || threadIdx.x != 0 || state->cycle_started == 0) {
    return;
  }
  const int record = state->output.restart_count++;
  state->output.restart_start[record] = state->cycle_start_iteration;
  state->output.restart_end[record] = state->cycle_end_iteration;
  state->output.restart_disposition[record] =
      state->terminal_code == kUnset ? kRestarted : state->terminal_code;
  state->cycle_started = 0;
}

__global__ void multi_block_copy_solution(int n, const double* current,
                                          double* output_solution) {
  const int global_thread = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int stride = static_cast<int>(gridDim.x * blockDim.x);
  for (int index = global_thread; index < n; index += stride) {
    output_solution[index] = current[index];
  }
}

const char* terminal_name(int code) {
  switch (code) {
    case kInitialResidualSatisfied:
      return "initial_residual_satisfied";
    case kConvergedScaledResidual:
      return "converged_scaled_residual";
    case kMaxIterations:
      return "max_iterations";
    case kArnoldiBreakdown:
      return "arnoldi_breakdown";
    case kRestarted:
      return "restarted";
    default:
      return "invalid";
  }
}

void print_double_vector(const double* values, int count) {
  std::cout << '[';
  for (int index = 0; index < count; ++index) {
    if (index != 0) {
      std::cout << ',';
    }
    std::cout << values[index];
  }
  std::cout << ']';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      throw std::runtime_error(
          "usage:engine_v2_fgmres_recurrence fixture.bin checkpoint.bin");
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
      throw std::runtime_error("fixture_open_failed");
    }
    std::array<char, 8> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input || magic != kMagic) {
      throw std::runtime_error("fixture_magic_invalid");
    }
    std::uint64_t n_unsigned = 0;
    std::uint64_t nnz_unsigned = 0;
    std::uint64_t case_count_unsigned = 0;
    read_scalar(input, n_unsigned);
    read_scalar(input, nnz_unsigned);
    read_scalar(input, case_count_unsigned);
    if (n_unsigned == 0 || n_unsigned > kMaximumFixtureDimension ||
        nnz_unsigned == 0 || case_count_unsigned != 2) {
      throw std::runtime_error("fixture_dimensions_invalid");
    }
    const int n = static_cast<int>(n_unsigned);
    const int fixture_case_count = static_cast<int>(case_count_unsigned);
    const auto nnz = static_cast<std::int64_t>(nnz_unsigned);
    std::vector<std::int64_t> row_ptr(static_cast<std::size_t>(n + 1));
    std::vector<std::int32_t> columns(static_cast<std::size_t>(nnz));
    std::vector<double> values(static_cast<std::size_t>(nnz));
    std::vector<double> right_hand_side(static_cast<std::size_t>(n));
    std::vector<double> scale(static_cast<std::size_t>(n));
    std::vector<double> initial_solution(static_cast<std::size_t>(n));
    std::vector<double> inverse_diagonal(static_cast<std::size_t>(n));
    read_vector(input, row_ptr);
    read_vector(input, columns);
    read_vector(input, values);
    read_vector(input, right_hand_side);
    read_vector(input, scale);
    read_vector(input, initial_solution);
    read_vector(input, inverse_diagonal);
    std::vector<CaseConfig> configurations(
        static_cast<std::size_t>(fixture_case_count));
    for (auto& config : configurations) {
      read_scalar(input, config.max_iterations);
      read_scalar(input, config.restart_length);
      read_scalar(input, config.relative_tolerance);
      read_scalar(input, config.absolute_tolerance);
      read_scalar(input, config.breakdown_tolerance);
    }
    if (input.peek() != std::ifstream::traits_type::eof() || row_ptr.front() != 0 ||
        row_ptr.back() != nnz || !std::is_sorted(row_ptr.begin(), row_ptr.end())) {
      throw std::runtime_error("fixture_csr_invalid");
    }
    for (const auto column : columns) {
      if (column < 0 || column >= n) {
        throw std::runtime_error("fixture_column_invalid");
      }
    }
    for (int row = 0; row < n; ++row) {
      int diagonal_count = 0;
      double diagonal = 0.0;
      for (std::int64_t position = row_ptr[row];
           position < row_ptr[row + 1]; ++position) {
        if (columns[position] == row) {
          ++diagonal_count;
          diagonal = values[position];
        }
      }
      const double scaled_diagonal = diagonal / scale[row];
      const double expected_inverse = 1.0 / scaled_diagonal;
      if (diagonal_count != 1 || !std::isfinite(scaled_diagonal) ||
          scaled_diagonal <= 0.0 || !std::isfinite(expected_inverse) ||
          inverse_diagonal[row] != expected_inverse) {
        throw std::runtime_error("fixture_preconditioner_binding_invalid");
      }
    }

    std::ifstream checkpoint_input(argv[2], std::ios::binary);
    if (!checkpoint_input) {
      throw std::runtime_error("checkpoint_open_failed");
    }
    std::array<char, 8> checkpoint_magic{};
    checkpoint_input.read(
        checkpoint_magic.data(),
        static_cast<std::streamsize>(checkpoint_magic.size()));
    if (!checkpoint_input || checkpoint_magic != kCheckpointMagic) {
      throw std::runtime_error("checkpoint_magic_invalid");
    }
    std::uint64_t checkpoint_free_count = 0;
    std::uint64_t checkpoint_iteration_count = 0;
    std::uint64_t checkpoint_matvec_count = 0;
    std::uint64_t checkpoint_next_restart_index = 0;
    double checkpoint_convergence_threshold = 0.0;
    read_scalar(checkpoint_input, checkpoint_free_count);
    read_scalar(checkpoint_input, checkpoint_iteration_count);
    read_scalar(checkpoint_input, checkpoint_matvec_count);
    read_scalar(checkpoint_input, checkpoint_next_restart_index);
    read_scalar(checkpoint_input, checkpoint_convergence_threshold);
    std::vector<double> checkpoint_solution(static_cast<std::size_t>(n));
    std::vector<double> checkpoint_residual(static_cast<std::size_t>(n));
    read_vector(checkpoint_input, checkpoint_solution);
    read_vector(checkpoint_input, checkpoint_residual);
    if (checkpoint_input.peek() != std::ifstream::traits_type::eof() ||
        checkpoint_free_count != static_cast<std::uint64_t>(n) ||
        checkpoint_iteration_count == 0 ||
        checkpoint_iteration_count >= configurations[1].max_iterations ||
        checkpoint_matvec_count != 1 + 2 * checkpoint_iteration_count ||
        checkpoint_next_restart_index == 0 ||
        !std::isfinite(checkpoint_convergence_threshold) ||
        checkpoint_convergence_threshold < 0.0) {
      throw std::runtime_error("checkpoint_boundary_invalid");
    }
    constexpr int execution_case_count = 3;
    configurations.push_back(configurations[1]);
    std::vector<ResumeConfig> resumes(execution_case_count);
    std::vector<double> resume_vectors(
        static_cast<std::size_t>(execution_case_count * 2 * n));
    ResumeConfig& checkpoint_resume = resumes[2];
    checkpoint_resume.enabled = 1;
    checkpoint_resume.iteration_count =
        static_cast<int>(checkpoint_iteration_count);
    checkpoint_resume.matvec_count = static_cast<int>(checkpoint_matvec_count);
    checkpoint_resume.next_restart_index =
        static_cast<int>(checkpoint_next_restart_index);
    checkpoint_resume.convergence_threshold =
        checkpoint_convergence_threshold;
    for (int index = 0; index < n; ++index) {
      resume_vectors[static_cast<std::size_t>(4 * n + index)] =
          checkpoint_solution[index];
      resume_vectors[static_cast<std::size_t>(5 * n + index)] =
          checkpoint_residual[index];
    }
    const std::uint64_t workspace_stride =
        static_cast<std::uint64_t>(2 * kMaximumRestart + 7) * n_unsigned;

    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index),
              "hipGetDeviceProperties");
    const auto device_lifecycle_started = std::chrono::steady_clock::now();
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");
    auto* d_row_ptr = allocate_and_copy(row_ptr, stream);
    auto* d_columns = allocate_and_copy(columns, stream);
    auto* d_values = allocate_and_copy(values, stream);
    auto* d_right_hand_side = allocate_and_copy(right_hand_side, stream);
    auto* d_scale = allocate_and_copy(scale, stream);
    auto* d_initial_solution = allocate_and_copy(initial_solution, stream);
    auto* d_inverse_diagonal = allocate_and_copy(inverse_diagonal, stream);
    auto* d_resume_vectors = allocate_and_copy(resume_vectors, stream);
    double* d_multi_workspace = nullptr;
    check_hip(hipMalloc(&d_multi_workspace,
                        execution_case_count * workspace_stride *
                            sizeof(double)),
              "hipMalloc_multi_workspace");
    check_hip(hipMemsetAsync(d_multi_workspace, 0,
                             execution_case_count * workspace_stride *
                                 sizeof(double),
                             stream),
              "hipMemsetAsync_multi_workspace");
    MultiBlockState* d_multi_states = nullptr;
    check_hip(hipMalloc(&d_multi_states,
                        execution_case_count * sizeof(MultiBlockState)),
              "hipMalloc_multi_states");
    check_hip(hipMemsetAsync(d_multi_states, 0,
                             execution_case_count * sizeof(MultiBlockState),
                             stream),
              "hipMemsetAsync_multi_states");
    double* d_multi_solutions = nullptr;
    check_hip(hipMalloc(&d_multi_solutions,
                        execution_case_count * n_unsigned * sizeof(double)),
              "hipMalloc_multi_solutions");
    check_hip(hipMemsetAsync(d_multi_solutions, 0,
                             execution_case_count * n_unsigned * sizeof(double),
                             stream),
              "hipMemsetAsync_multi_solutions");
    double* d_multi_partials = nullptr;
    check_hip(hipMalloc(&d_multi_partials,
                        2 * kOperatorBlocksPerCase * sizeof(double)),
              "hipMalloc_multi_partials");
    check_hip(hipMemsetAsync(d_multi_partials, 0,
                             2 * kOperatorBlocksPerCase * sizeof(double),
                             stream),
              "hipMemsetAsync_multi_partials");

    const std::uint64_t h2d_bytes =
        row_ptr.size() * sizeof(std::int64_t) +
        columns.size() * sizeof(std::int32_t) +
        values.size() * sizeof(double) +
        right_hand_side.size() * sizeof(double) +
        scale.size() * sizeof(double) +
        initial_solution.size() * sizeof(double) +
        inverse_diagonal.size() * sizeof(double) +
        resume_vectors.size() * sizeof(double);
    const std::uint64_t tracked_peak_device_allocation_bytes =
        h2d_bytes + execution_case_count * workspace_stride * sizeof(double) +
        execution_case_count * sizeof(MultiBlockState) +
        execution_case_count * n_unsigned * sizeof(double) +
        2 * kOperatorBlocksPerCase * sizeof(double);

    std::uint64_t multi_block_kernel_invocation_count = 0;
#define LAUNCH_MULTI_BLOCK(kernel, grid, block, ...)                         \
    do {                                                                    \
      hipLaunchKernelGGL(kernel, grid, block, 0, stream, __VA_ARGS__);      \
      ++multi_block_kernel_invocation_count;                                \
    } while (false)

    for (int case_index = 0; case_index < execution_case_count; ++case_index) {
      const CaseConfig config = configurations[case_index];
      const ResumeConfig resume = resumes[case_index];
      MultiBlockState* const state = d_multi_states + case_index;
      double* const case_workspace =
          d_multi_workspace + static_cast<std::uint64_t>(case_index) *
                                  workspace_stride;
      double* const current = case_workspace;
      double* const recurrence_residual = current + n;
      double* const cycle_solution = recurrence_residual + n;
      double* const candidate = cycle_solution + n;
      double* const work = candidate + n;
      double* const internal = work + n;
      double* const basis_v = internal + n;
      double* const basis_z = basis_v + (kMaximumRestart + 1) * n;
      const double* const resume_solution =
          d_resume_vectors + static_cast<std::uint64_t>(case_index) * 2 * n;
      const double* const resume_residual = resume_solution + n;
      double* const case_solution =
          d_multi_solutions + static_cast<std::uint64_t>(case_index) * n;
      const int first_iteration = resume.enabled ? resume.iteration_count : 0;

      LAUNCH_MULTI_BLOCK(multi_block_initialize_state, dim3(1), dim3(1),
                         state, config, resume);
      LAUNCH_MULTI_BLOCK(
          multi_block_initialize_vectors, dim3(kOperatorBlocksPerCase),
          dim3(kThreadsPerCase), n, resume.enabled, d_initial_solution,
          resume_solution, resume_residual, current, recurrence_residual);
      if (!resume.enabled) {
        LAUNCH_MULTI_BLOCK(
            multi_block_spmv, dim3(kOperatorBlocksPerCase),
            dim3(kThreadsPerCase), n, first_iteration, 1, d_row_ptr,
            d_columns, d_values, current, internal, state);
        LAUNCH_MULTI_BLOCK(
            multi_block_residual, dim3(kOperatorBlocksPerCase),
            dim3(kThreadsPerCase), n, first_iteration, d_right_hand_side,
            d_scale, internal, recurrence_residual, state);
      }
      LAUNCH_MULTI_BLOCK(
          multi_block_norm_partials, dim3(kOperatorBlocksPerCase),
          dim3(kThreadsPerCase), n, first_iteration, recurrence_residual,
          d_multi_partials, state);
      LAUNCH_MULTI_BLOCK(multi_block_norm_finalize, dim3(1),
                         dim3(kThreadsPerCase), first_iteration, 0, -1,
                         d_multi_partials, state);
      LAUNCH_MULTI_BLOCK(multi_block_finalize_initial, dim3(1), dim3(1),
                         resume.enabled, config, state);

      for (int cycle_start = first_iteration;
           cycle_start < static_cast<int>(config.max_iterations);
           cycle_start += static_cast<int>(config.restart_length)) {
        const int remaining =
            static_cast<int>(config.max_iterations) - cycle_start;
        const int capacity =
            std::min(static_cast<int>(config.restart_length), remaining);
        LAUNCH_MULTI_BLOCK(multi_block_begin_cycle, dim3(1),
                           dim3(kThreadsPerCase), cycle_start, capacity,
                           config, state);
        LAUNCH_MULTI_BLOCK(
            multi_block_begin_cycle_vectors, dim3(kOperatorBlocksPerCase),
            dim3(kThreadsPerCase), n, cycle_start, current,
            recurrence_residual, cycle_solution, basis_v, state);

        for (int inner = 0; inner < capacity; ++inner) {
          const int expected_iteration = cycle_start + inner;
          LAUNCH_MULTI_BLOCK(
              multi_block_apply_preconditioner,
              dim3(kOperatorBlocksPerCase), dim3(kThreadsPerCase), n,
              expected_iteration, inner, d_inverse_diagonal, basis_v, basis_z,
              state);
          LAUNCH_MULTI_BLOCK(
              multi_block_scaled_spmv, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, expected_iteration, d_row_ptr,
              d_columns, d_values, d_scale, basis_z + inner * n, work, state);
          for (int pass = 0; pass < 2; ++pass) {
            for (int basis = 0; basis <= inner; ++basis) {
              LAUNCH_MULTI_BLOCK(
                  multi_block_dot_partials,
                  dim3(kOperatorBlocksPerCase), dim3(kThreadsPerCase), n,
                  expected_iteration, basis_v + basis * n, work,
                  d_multi_partials, state);
              LAUNCH_MULTI_BLOCK(
                  multi_block_dot_finalize, dim3(1),
                  dim3(kThreadsPerCase), expected_iteration, basis, inner,
                  d_multi_partials, state);
              LAUNCH_MULTI_BLOCK(
                  multi_block_axpy_work, dim3(kOperatorBlocksPerCase),
                  dim3(kThreadsPerCase), n, expected_iteration, basis, basis_v,
                  work, state);
            }
          }
          LAUNCH_MULTI_BLOCK(
              multi_block_norm_partials, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, expected_iteration, work,
              d_multi_partials, state);
          LAUNCH_MULTI_BLOCK(multi_block_norm_finalize, dim3(1),
                             dim3(kThreadsPerCase), expected_iteration, 1,
                             inner,
                             d_multi_partials, state);
          LAUNCH_MULTI_BLOCK(
              multi_block_normalize_next, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, expected_iteration, inner, config,
              work, basis_v, state);
          LAUNCH_MULTI_BLOCK(multi_block_givens_back_substitution, dim3(1),
                             dim3(1), expected_iteration, inner, config,
                             state);
          LAUNCH_MULTI_BLOCK(
              multi_block_build_candidate, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, expected_iteration, inner, current,
              cycle_solution, basis_z, candidate, state);
          LAUNCH_MULTI_BLOCK(multi_block_increment_iteration, dim3(1),
                             dim3(1), expected_iteration, state);
          const int completed_iteration = expected_iteration + 1;
          LAUNCH_MULTI_BLOCK(
              multi_block_spmv, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, completed_iteration, 1, d_row_ptr,
              d_columns, d_values, candidate, internal, state);
          LAUNCH_MULTI_BLOCK(
              multi_block_residual, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, completed_iteration,
              d_right_hand_side, d_scale, internal, recurrence_residual,
              state);
          LAUNCH_MULTI_BLOCK(
              multi_block_norm_partials, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, completed_iteration,
              recurrence_residual, d_multi_partials, state);
          LAUNCH_MULTI_BLOCK(multi_block_norm_finalize, dim3(1),
                             dim3(kThreadsPerCase), completed_iteration, 0, -1,
                             d_multi_partials, state);
          LAUNCH_MULTI_BLOCK(
              multi_block_update_current, dim3(kOperatorBlocksPerCase),
              dim3(kThreadsPerCase), n, completed_iteration, candidate,
              current, state);
          LAUNCH_MULTI_BLOCK(multi_block_finalize_iteration, dim3(1),
                             dim3(1), completed_iteration, config, state);
        }
        LAUNCH_MULTI_BLOCK(multi_block_finish_cycle, dim3(1), dim3(1),
                           state);
      }
      LAUNCH_MULTI_BLOCK(
          multi_block_copy_solution, dim3(kOperatorBlocksPerCase),
          dim3(kThreadsPerCase), n, current, case_solution);
    }
#undef LAUNCH_MULTI_BLOCK
    check_hip(hipGetLastError(), "multi_block_fgmres_sequence");

    std::vector<MultiBlockState> multi_states(
        static_cast<std::size_t>(execution_case_count));
    std::vector<double> multi_solutions(
        static_cast<std::size_t>(execution_case_count * n));
    check_hip(hipMemcpyAsync(multi_states.data(), d_multi_states,
                             multi_states.size() * sizeof(MultiBlockState),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_multi_states");
    check_hip(hipMemcpyAsync(multi_solutions.data(), d_multi_solutions,
                             multi_solutions.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_multi_solutions");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");
    const auto device_lifecycle_finished = std::chrono::steady_clock::now();
    const double device_lifecycle_wall_time_ms =
        std::chrono::duration<double, std::milli>(device_lifecycle_finished -
                                                  device_lifecycle_started)
            .count();
    const std::uint64_t d2h_bytes =
        multi_states.size() * sizeof(MultiBlockState) +
        multi_solutions.size() * sizeof(double);
    const std::uint64_t preconditioner_apply_count =
        static_cast<std::uint64_t>(multi_states[0].output.iteration_count) +
        static_cast<std::uint64_t>(multi_states[1].output.iteration_count) +
        static_cast<std::uint64_t>(multi_states[2].output.iteration_count -
                                   checkpoint_resume.iteration_count);
    const std::uint64_t executed_matvec_count =
        static_cast<std::uint64_t>(multi_states[0].output.matvec_count) +
        static_cast<std::uint64_t>(multi_states[1].output.matvec_count) +
        static_cast<std::uint64_t>(multi_states[2].output.matvec_count -
                                   checkpoint_resume.matvec_count);

    check_hip(hipFree(d_row_ptr), "hipFree_row_ptr");
    check_hip(hipFree(d_columns), "hipFree_columns");
    check_hip(hipFree(d_values), "hipFree_values");
    check_hip(hipFree(d_right_hand_side), "hipFree_right_hand_side");
    check_hip(hipFree(d_scale), "hipFree_scale");
    check_hip(hipFree(d_initial_solution), "hipFree_initial_solution");
    check_hip(hipFree(d_inverse_diagonal), "hipFree_inverse_diagonal");
    check_hip(hipFree(d_resume_vectors), "hipFree_resume_vectors");
    check_hip(hipFree(d_multi_workspace), "hipFree_multi_workspace");
    check_hip(hipFree(d_multi_states), "hipFree_multi_states");
    check_hip(hipFree(d_multi_solutions), "hipFree_multi_solutions");
    check_hip(hipFree(d_multi_partials), "hipFree_multi_partials");
    check_hip(hipStreamDestroy(stream), "hipStreamDestroy");

    const char* case_ids[2] = {"converged_full_cycle", "restart_max_iterations"};
    std::cout << std::setprecision(17);
    std::cout
        << "{\"schema_version\":\"engine-v2-hip-fgmres-recurrence-output.v1\","
        << "\"runtime_status\":\"success\",\"runtime_status_code\":0,"
        << "\"backend\":\"amd_rocm_hip\",\"cpu_backend\":false,"
        << "\"same_stream_ordering\":true,"
        << "\"mid_recurrence_host_transfer_count\":0,"
        << "\"blocking_d2h_synchronization_count\":1,"
        << "\"kernel_invocation_count\":"
        << multi_block_kernel_invocation_count << ','
        << "\"multi_block_kernel_invocation_count\":"
        << multi_block_kernel_invocation_count << ','
        << "\"operator_blocks_per_case\":" << kOperatorBlocksPerCase << ','
        << "\"recurrence_execution_profile\":"
           "\"same_stream_fixed_kernel_sequence_device_guarded.v1\","
        << "\"checkpoint_h2d_transfer_count\":1,"
        << "\"checkpoint_completed_iteration_replay_count\":0,"
        << "\"device_resident_full_recurrence_probe\":true,"
        << "\"production_recurrence_claim\":false,"
        << "\"telemetry_profile\":\"bounded_device_lifecycle_exact_counters.v1\","
        << "\"executed_matvec_count\":" << executed_matvec_count << ','
        << "\"preconditioner_apply_count\":"
        << preconditioner_apply_count << ','
        << "\"h2d_bytes\":" << h2d_bytes << ','
        << "\"d2h_bytes\":" << d2h_bytes << ','
        << "\"tracked_peak_device_allocation_bytes\":"
        << tracked_peak_device_allocation_bytes << ','
        << "\"device_lifecycle_wall_time_ms\":"
        << device_lifecycle_wall_time_ms << ','
        << "\"preconditioner_profile\":"
           "\"operator_derived_left_scaled_jacobi_right.v1\","
        << "\"threads_per_case\":" << kThreadsPerCase << ','
        << "\"reduction_profile\":\"fixed_block_binary_tree_fp64_probe.v1\","
        << "\"krylov_workspace_profile\":"
           "\"device_global_dynamic_dimension_fp64.v1\","
        << "\"workspace_dimension\":" << n << ','
        << "\"workspace_doubles_per_case\":" << workspace_stride << ','
        << "\"cooperative_launch_supported\":"
        << (properties.cooperativeLaunch ? "true" : "false") << ','
        << "\"device_status_to_terminal_state\":true,"
        << "\"device_index\":" << device_index << ','
        << "\"device_name\":\"" << properties.name << "\","
        << "\"gcn_arch_name\":\"" << properties.gcnArchName << "\","
        << "\"cases\":[";
    for (int case_index = 0; case_index < fixture_case_count; ++case_index) {
      if (case_index != 0) {
        std::cout << ',';
      }
      const auto& output = multi_states[case_index].output;
      std::cout << "{\"case_id\":\"" << case_ids[case_index] << "\","
                << "\"runtime_status_code\":" << output.status_code << ','
                << "\"terminal_reason\":\""
                << terminal_name(output.terminal_code) << "\","
                << "\"converged\":" << (output.converged ? "true" : "false")
                << ",\"iteration_count\":" << output.iteration_count
                << ",\"matvec_count\":" << output.matvec_count
                << ",\"restart_count\":" << output.restart_count
                << ",\"convergence_threshold_scaled_l2\":"
                << output.convergence_threshold << ",\"solution\":";
      print_double_vector(
          &multi_solutions[static_cast<std::size_t>(case_index * n)], n);
      std::cout << ",\"scaled_l2_history\":";
      print_double_vector(output.scaled_l2_history, output.history_count);
      std::cout << ",\"scaled_linf_history\":";
      print_double_vector(output.scaled_linf_history, output.history_count);
      std::cout << ",\"restart_history\":[";
      for (int record = 0; record < output.restart_count; ++record) {
        if (record != 0) {
          std::cout << ',';
        }
        const int start = output.restart_start[record];
        const int end = output.restart_end[record];
        std::cout << "{\"start_iteration\":" << start
                  << ",\"end_iteration\":" << end
                  << ",\"iteration_count\":" << end - start
                  << ",\"disposition\":\""
                  << terminal_name(output.restart_disposition[record]) << "\"}";
      }
      std::cout << "]}";
    }
    const auto& resumed = multi_states[2].output;
    std::cout << "],\"checkpoint_resume\":{"
              << "\"case_id\":\"restart_max_iterations\","
              << "\"runtime_status_code\":" << resumed.status_code << ','
              << "\"artifact_loaded\":true,"
              << "\"device_resident_suffix_recurrence\":true,"
              << "\"completed_iteration_replay_count\":"
              << resumed.completed_iteration_replay_count << ','
              << "\"resumed_from_iteration\":"
              << resumed.resumed_from_iteration << ','
              << "\"restart_index_base\":" << resumed.restart_index_base << ','
              << "\"terminal_reason\":\""
              << terminal_name(resumed.terminal_code) << "\","
              << "\"converged\":"
              << (resumed.converged ? "true" : "false")
              << ",\"iteration_count\":" << resumed.iteration_count
              << ",\"matvec_count\":" << resumed.matvec_count
              << ",\"suffix_restart_count\":" << resumed.restart_count
              << ",\"convergence_threshold_scaled_l2\":"
              << resumed.convergence_threshold << ",\"solution\":";
    print_double_vector(
        &multi_solutions[static_cast<std::size_t>(2 * n)], n);
    std::cout << ",\"scaled_l2_suffix_history\":";
    print_double_vector(resumed.scaled_l2_history, resumed.history_count);
    std::cout << ",\"scaled_linf_suffix_history\":";
    print_double_vector(resumed.scaled_linf_history, resumed.history_count);
    std::cout << ",\"restart_suffix_history\":[";
    for (int record = 0; record < resumed.restart_count; ++record) {
      if (record != 0) {
        std::cout << ',';
      }
      const int start = resumed.restart_start[record];
      const int end = resumed.restart_end[record];
      std::cout << "{\"start_iteration\":" << start
                << ",\"end_iteration\":" << end
                << ",\"iteration_count\":" << end - start
                << ",\"disposition\":\""
                << terminal_name(resumed.restart_disposition[record]) << "\"}";
    }
    std::cout << "]}}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr
        << "{\"schema_version\":\"engine-v2-hip-fgmres-recurrence-output.v1\","
        << "\"runtime_status\":\"error\",\"runtime_status_code\":1,"
        << "\"error\":\"" << error.what() << "\"}\n";
    return 1;
  }
}
