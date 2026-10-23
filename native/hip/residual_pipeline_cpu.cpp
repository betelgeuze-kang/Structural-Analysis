// Optimized multicore CSR reference for the same fixed-operator state sequence.
// One persistent OpenMP team spans all residual and state-update stages.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <limits>
#include <vector>
#include <omp.h>

namespace {
struct FixedOperator {
  std::size_t n;
  std::vector<std::int64_t> row, column;
  std::vector<double> value, external;
};
}

extern "C" int structural_cpu_fixed_operator_create_v1(
    std::size_t n, std::size_t nnz, const std::int64_t* row,
    const std::int64_t* column, const double* value, const double* external,
    void** result) noexcept {
  if (!result || reinterpret_cast<std::uintptr_t>(result) % alignof(void*)) return 1;
  if (n < 12 || n > 196608 || nnz == 0 || nnz > n * 32 ||
      !row || !column || !value || !external) return 1;
  if (reinterpret_cast<std::uintptr_t>(row) % alignof(std::int64_t) ||
      reinterpret_cast<std::uintptr_t>(column) % alignof(std::int64_t) ||
      reinterpret_cast<std::uintptr_t>(value) % alignof(double) ||
      reinterpret_cast<std::uintptr_t>(external) % alignof(double)) return 1;
  const auto overlaps = [](const void* a, std::size_t na,
                           const void* b, std::size_t nb) {
    const auto x = reinterpret_cast<std::uintptr_t>(a);
    const auto y = reinterpret_cast<std::uintptr_t>(b);
    const auto maximum = std::numeric_limits<std::uintptr_t>::max();
    return x > maximum - na || y > maximum - nb ||
        (x < y + nb && y < x + na);
  };
  // Admit every output/input span before writing even the failure sentinel.
  // In particular, a handle slot inside caller-owned CSR data is not writable.
  if (overlaps(result, sizeof(*result), row, (n + 1) * sizeof(*row)) ||
      overlaps(result, sizeof(*result), column, nnz * sizeof(*column)) ||
      overlaps(result, sizeof(*result), value, nnz * sizeof(*value)) ||
      overlaps(result, sizeof(*result), external, n * sizeof(*external))) return 1;
  *result = nullptr;
  if (row[0] != 0 || row[n] != static_cast<std::int64_t>(nnz)) return 1;
  for (std::size_t i = 0; i < n; ++i) {
    if (row[i] < 0 || row[i] > row[i + 1] ||
        !std::isfinite(external[i])) return 2;
  }
  for (std::size_t k = 0; k < nnz; ++k)
    if (column[k] < 0 || column[k] >= static_cast<std::int64_t>(n) ||
        !std::isfinite(value[k])) return 2;
  try {
    auto op = std::make_unique<FixedOperator>();
    op->n = n;
    op->row.assign(row, row + n + 1);
    op->column.assign(column, column + nnz);
    op->value.assign(value, value + nnz);
    op->external.assign(external, external + n);
    *result = op.release();
    return 0;
  } catch (...) { return 3; }
}

extern "C" int structural_cpu_fixed_residual_sequence_v1(
    void* raw, const double* initial, std::size_t batch, int steps,
    int workers, double omega, double* state, double* residual,
    int* observed_workers) noexcept {
  auto* op = reinterpret_cast<FixedOperator*>(raw);
  if (!op || !initial || !state || !residual || !observed_workers ||
      batch < 1 || batch > 64 || steps < 1 || steps > 128 ||
      workers < 1 || workers > 12 || !std::isfinite(omega) ||
      omega <= 0.0 || omega > 1.0) return 1;
  const std::size_t total = batch * op->n;
  const double* buffers[] = {initial, state, residual};
  for (const double* p : buffers)
    if (reinterpret_cast<std::uintptr_t>(p) % alignof(double)) return 1;
  if (reinterpret_cast<std::uintptr_t>(observed_workers) % alignof(int)) return 1;
  const auto overlaps = [](const void* a, std::size_t na, const void* b, std::size_t nb) {
    const auto x = reinterpret_cast<std::uintptr_t>(a);
    const auto y = reinterpret_cast<std::uintptr_t>(b);
    const auto maximum = std::numeric_limits<std::uintptr_t>::max();
    return x > maximum - na || y > maximum - nb ||
        (x < y + nb && y < x + na);
  };
  const auto bytes = total * sizeof(double);
  if (overlaps(state, bytes, residual, bytes) || overlaps(initial, bytes, state, bytes) ||
      overlaps(initial, bytes, residual, bytes) ||
      overlaps(observed_workers, sizeof(int), initial, bytes) ||
      overlaps(observed_workers, sizeof(int), state, bytes) ||
      overlaps(observed_workers, sizeof(int), residual, bytes)) return 1;
  // Both CPU/HIP timing adapters consume caller-validated generated finite
  // states. Output finiteness/parity checks occur outside both timed regions.
  std::copy(initial, initial + total, state);
  #pragma omp parallel num_threads(workers)
  {
    #pragma omp single
    *observed_workers = omp_get_num_threads();
    for (int step = 0; step <= steps; ++step) {
      #pragma omp for schedule(static)
      for (std::size_t i = 0; i < total; ++i) {
        const std::size_t row = i % op->n;
        const std::size_t base = i - row;
        double sum = 0.0;
        for (auto k = op->row[row]; k < op->row[row + 1]; ++k)
          sum += op->value[k] * state[base + op->column[k]];
        residual[i] = sum - op->external[row];
      }
      if (step < steps) {
        #pragma omp for schedule(static)
        for (std::size_t i = 0; i < total; ++i)
          state[i] -= omega * residual[i];
      }
    }
  }
  return 0;
}

extern "C" int structural_cpu_fixed_operator_destroy_v1(void* raw) noexcept {
  if (!raw) return 1;
  delete reinterpret_cast<FixedOperator*>(raw);
  return 0;
}
