// Optional resident CSR execution of one fixed, already assembled linear map.
// No material/Newton/RC solver routing, convergence claim, or CPU fallback.
#include <hip/hip_runtime.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
thread_local char last_error[512] = {};

int failure(int code, const char* text) noexcept {
  std::snprintf(last_error, sizeof(last_error), "%s", text);
  return code;
}

void checked(hipError_t code, const char* operation) {
  if (code != hipSuccess)
    throw std::runtime_error(std::string(operation) + ": " + hipGetErrorString(code));
}

double elapsed_ms(Clock::time_point a, Clock::time_point b) {
  return std::chrono::duration<double, std::milli>(b - a).count();
}

struct Span {
  const void* pointer;
  std::size_t bytes;
  std::size_t alignment;
};

bool admitted(const Span* spans, std::size_t count) noexcept {
  const auto maximum = std::numeric_limits<std::uintptr_t>::max();
  for (std::size_t i = 0; i < count; ++i) {
    const auto begin = reinterpret_cast<std::uintptr_t>(spans[i].pointer);
    if (!begin || begin % spans[i].alignment || begin > maximum - spans[i].bytes)
      return false;
    for (std::size_t j = 0; j < i; ++j) {
      const auto other = reinterpret_cast<std::uintptr_t>(spans[j].pointer);
      if (begin < other + spans[j].bytes && other < begin + spans[i].bytes)
        return false;
    }
  }
  return true;
}

struct DeviceScope {
  int previous = 0;
  bool changed = false;
  explicit DeviceScope(int device) {
    checked(hipGetDevice(&previous), "get CSR device");
    if (previous != device) {
      checked(hipSetDevice(device), "select CSR device");
      changed = true;
    }
  }
  ~DeviceScope() noexcept {
    if (changed) (void)hipSetDevice(previous);
  }
};

void free_device(void* pointer) noexcept {
  if (pointer) (void)hipFree(pointer);
}

struct Scratch {
  double* state_a = nullptr;
  double* state_b = nullptr;
  double* residual = nullptr;
  std::size_t capacity = 0;
  std::vector<double> host_state, host_residual;

  void clear() noexcept {
    free_device(state_a);
    free_device(state_b);
    free_device(residual);
    state_a = state_b = residual = nullptr;
    capacity = 0;
  }
  ~Scratch() noexcept { clear(); }
};

struct Operator {
  long long n = 0;
  int device = 0;
  long long* row = nullptr;
  long long* column = nullptr;
  double* value = nullptr;
  double* external = nullptr;
  Scratch scratch;
  bool busy = false;  // Every access is protected by registry_mutex.

  ~Operator() noexcept {
    int previous = 0;
    const bool restore = hipGetDevice(&previous) == hipSuccess && previous != device;
    if (restore) (void)hipSetDevice(device);
    scratch.clear();
    free_device(row);
    free_device(column);
    free_device(value);
    free_device(external);
    if (restore) (void)hipSetDevice(previous);
  }
};

std::mutex registry_mutex;
std::unordered_map<void*, std::shared_ptr<Operator>> registry;
std::uintptr_t next_token = 16;

struct Lease {
  std::shared_ptr<Operator> op;
  explicit Lease(std::shared_ptr<Operator> value) : op(std::move(value)) {}
  Lease(const Lease&) = delete;
  Lease& operator=(const Lease&) = delete;
  ~Lease() noexcept {
    if (op) {
      std::lock_guard<std::mutex> guard(registry_mutex);
      op->busy = false;
    }
  }
};

template <typename T>
void allocate_copy(T*& output, const T* input, std::size_t count) {
  checked(hipMalloc(reinterpret_cast<void**>(&output), count * sizeof(T)), "allocate CSR operator");
  checked(hipMemcpy(output, input, count * sizeof(T), hipMemcpyHostToDevice), "copy CSR operator");
}

void ensure_scratch(Operator& op, std::size_t count) {
  if (op.scratch.capacity >= count) return;
  Scratch replacement;
  checked(hipMalloc(reinterpret_cast<void**>(&replacement.state_a), count * sizeof(double)), "allocate CSR state A");
  checked(hipMalloc(reinterpret_cast<void**>(&replacement.state_b), count * sizeof(double)), "allocate CSR state B");
  checked(hipMalloc(reinterpret_cast<void**>(&replacement.residual), count * sizeof(double)), "allocate CSR residual");
  replacement.host_state.resize(count);
  replacement.host_residual.resize(count);
  // Publish all new scratch together. Failure above leaves old capacity usable.
  std::swap(op.scratch.state_a, replacement.state_a);
  std::swap(op.scratch.state_b, replacement.state_b);
  std::swap(op.scratch.residual, replacement.residual);
  op.scratch.host_state.swap(replacement.host_state);
  op.scratch.host_residual.swap(replacement.host_residual);
  op.scratch.capacity = count;
}

struct Events {
  hipEvent_t start = nullptr, stop = nullptr;
  Events() {
    const auto first = hipEventCreate(&start);
    if (first != hipSuccess) {
      if (start) (void)hipEventDestroy(start);
      start = nullptr;
      checked(first, "create CSR start event");
    }
    const auto code = hipEventCreate(&stop);
    if (code != hipSuccess) {
      (void)hipEventDestroy(start);
      start = nullptr;
      checked(code, "create CSR stop event");
    }
  }
  ~Events() noexcept {
    if (start) (void)hipEventDestroy(start);
    if (stop) (void)hipEventDestroy(stop);
  }
};

struct DeviceWork {
  bool pending = false;
  ~DeviceWork() noexcept {
    // A failed launch/wait must finish outstanding work before scratch can be
    // reused, grown, or destroyed after the busy lease is released.
    if (pending) (void)hipDeviceSynchronize();
  }
};
}  // namespace

__global__ void structural_csr_fixed_step_kernel(
    const long long* row, const long long* column, const double* value,
    const double* external, const double* source, double* destination,
    double* residual, long long n, long long total, double omega, bool update) {
  const auto index = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= total) return;
  const long long equation = index % n;
  const long long base = index - equation;
  double sum = 0.0;
  for (long long entry = row[equation]; entry < row[equation + 1]; ++entry)
    sum += value[entry] * source[base + column[entry]];
  const double difference = sum - external[equation];
  if (update)
    destination[index] = source[index] - omega * difference;
  else
    residual[index] = difference;
}

extern "C" const char* structural_hip_csr_residual_last_error_v1() noexcept {
  return last_error;
}

extern "C" int structural_hip_csr_residual_create_v1(
    long long n, long long nnz, const long long* row, const long long* column,
    const double* value, const double* external, void** out_handle) noexcept {
  last_error[0] = '\0';
  if (n < 12 || n > 196608 || nnz < 1 || nnz > 32 * n)
    return failure(-1, "invalid bounded CSR dimensions");
  const Span spans[] = {
      {row, static_cast<std::size_t>(n + 1) * 8, alignof(long long)},
      {column, static_cast<std::size_t>(nnz) * 8, alignof(long long)},
      {value, static_cast<std::size_t>(nnz) * 8, alignof(double)},
      {external, static_cast<std::size_t>(n) * 8, alignof(double)},
      {out_handle, sizeof(void*), alignof(void*)},
  };
  // No caller memory, including the failure sentinel, is written before this.
  if (!admitted(spans, 5)) return failure(-1, "unaligned, overflowing or overlapping CSR create buffers");
  *out_handle = nullptr;
  if (row[0] != 0 || row[n] != nnz)
    return failure(-1, "invalid CSR row endpoints");
  for (long long i = 0; i < n; ++i)
    if (row[i] < 0 || row[i] > row[i + 1] || row[i] > nnz || !std::isfinite(external[i]))
      return failure(-1, "invalid CSR rows or nonfinite external vector");
  for (long long k = 0; k < nnz; ++k)
    if (column[k] < 0 || column[k] >= n || !std::isfinite(value[k]))
      return failure(-1, "invalid CSR column or nonfinite value");
  try {
    auto op = std::make_shared<Operator>();
    op->n = n;
    checked(hipGetDevice(&op->device), "get CSR operator device");
    allocate_copy(op->row, row, static_cast<std::size_t>(n + 1));
    allocate_copy(op->column, column, static_cast<std::size_t>(nnz));
    allocate_copy(op->value, value, static_cast<std::size_t>(nnz));
    allocate_copy(op->external, external, static_cast<std::size_t>(n));
    std::lock_guard<std::mutex> guard(registry_mutex);
    if (next_token > std::numeric_limits<std::uintptr_t>::max() - 16)
      return failure(-2, "CSR opaque handle token space exhausted");
    void* token = reinterpret_cast<void*>(next_token);
    next_token += 16;
    registry.emplace(token, std::move(op));
    *out_handle = token;
    return 0;
  } catch (const std::exception& error) {
    return failure(-2, error.what());
  } catch (...) {
    return failure(-2, "CSR operator creation failed");
  }
}

extern "C" int structural_hip_csr_residual_evaluate_v1(
    void* handle, const double* initial, long long batch, int steps,
    double omega, double* state, double* residual, double* phase_ms) noexcept {
  last_error[0] = '\0';
  try {
    std::shared_ptr<Operator> op;
    {
      std::lock_guard<std::mutex> guard(registry_mutex);
      const auto entry = registry.find(handle);
      if (entry == registry.end()) return failure(-1, "unknown or destroyed CSR handle");
      op = entry->second;
      if (op->busy) return failure(-3, "CSR resident handle is already in use");
      op->busy = true;
    }
    Lease lease(op);
    if (batch < 1 || batch > 64 || steps < 1 || steps > 128 ||
        !std::isfinite(omega) || omega <= 0.0 || omega > 1.0)
      return failure(-1, "invalid bounded CSR sequence arguments");
    const auto total = static_cast<std::size_t>(batch) * static_cast<std::size_t>(op->n);
    const auto bytes = total * sizeof(double);
    const Span spans[] = {
        {initial, bytes, alignof(double)}, {state, bytes, alignof(double)},
        {residual, bytes, alignof(double)}, {phase_ms, 6 * sizeof(double), alignof(double)},
    };
    if (!admitted(spans, 4)) return failure(-1, "unaligned, overflowing or overlapping CSR sequence buffers");
    for (std::size_t i = 0; i < total; ++i)
      if (!std::isfinite(initial[i])) return failure(-1, "nonfinite CSR initial state");
    DeviceScope device(op->device);
    Events events;
    DeviceWork work;
    const auto started = Clock::now();
    ensure_scratch(*op, total);
    const auto allocated = Clock::now();
    checked(hipMemcpy(op->scratch.state_a, initial, bytes, hipMemcpyHostToDevice), "CSR initial H2D");
    const auto copied = Clock::now();
    checked(hipEventRecord(events.start), "record CSR start");
    constexpr int block = 256;
    const dim3 grid((total + block - 1) / block);
    double* source = op->scratch.state_a;
    double* destination = op->scratch.state_b;
    for (int step = 0; step < steps; ++step) {
      work.pending = true;
      hipLaunchKernelGGL(structural_csr_fixed_step_kernel, grid, dim3(block), 0, 0,
          op->row, op->column, op->value, op->external, source, destination,
          op->scratch.residual, op->n, static_cast<long long>(total), omega, true);
      checked(hipGetLastError(), "CSR fused SpMV/update kernel");
      std::swap(source, destination);
    }
    work.pending = true;
    hipLaunchKernelGGL(structural_csr_fixed_step_kernel, grid, dim3(block), 0, 0,
        op->row, op->column, op->value, op->external, source, destination,
        op->scratch.residual, op->n, static_cast<long long>(total), omega, false);
    checked(hipGetLastError(), "CSR final residual kernel");
    checked(hipEventRecord(events.stop), "record CSR stop");
    checked(hipEventSynchronize(events.stop), "wait CSR final residual");
    work.pending = false;
    float kernel_ms = 0.0f;
    checked(hipEventElapsedTime(&kernel_ms, events.start, events.stop), "measure CSR kernel interval");
    const auto completed = Clock::now();
    checked(hipMemcpy(op->scratch.host_state.data(), source, bytes, hipMemcpyDeviceToHost), "CSR final state D2H");
    checked(hipMemcpy(op->scratch.host_residual.data(), op->scratch.residual, bytes, hipMemcpyDeviceToHost), "CSR final residual D2H");
    for (std::size_t i = 0; i < total; ++i)
      if (!std::isfinite(op->scratch.host_state[i]) || !std::isfinite(op->scratch.host_residual[i]))
        return failure(-2, "nonfinite CSR sequence output; caller outputs remain unchanged");
    std::memcpy(state, op->scratch.host_state.data(), bytes);
    std::memcpy(residual, op->scratch.host_residual.data(), bytes);
    const auto committed = Clock::now();
    const double phases[] = {
        elapsed_ms(started, allocated), elapsed_ms(allocated, copied), kernel_ms,
        elapsed_ms(copied, completed), elapsed_ms(completed, committed), elapsed_ms(started, committed),
    };
    std::memcpy(phase_ms, phases, sizeof(phases));
    return 0;
  } catch (const std::exception& error) {
    return failure(-2, error.what());
  } catch (...) {
    return failure(-2, "CSR resident sequence failed");
  }
}

extern "C" int structural_hip_csr_residual_destroy_v1(void* handle) noexcept {
  last_error[0] = '\0';
  try {
    std::shared_ptr<Operator> removed;
    {
      std::lock_guard<std::mutex> guard(registry_mutex);
      const auto entry = registry.find(handle);
      if (entry == registry.end()) return failure(-1, "unknown or destroyed CSR handle");
      if (entry->second->busy) return failure(-3, "CSR resident handle is already in use");
      removed = std::move(entry->second);
      registry.erase(entry);
    }
    // The last shared owner and all device allocations are released outside
    // the registry lock. Opaque tokens are never reused (no stale-pointer ABA).
    removed.reset();
    return 0;
  } catch (...) {
    return failure(-2, "CSR handle destruction failed");
  }
}
