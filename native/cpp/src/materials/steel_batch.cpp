#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <omp.h>

namespace { thread_local int last_workers = 0; }

extern "C" int sa_steel_batch_last_workers_v1() noexcept { return last_workers; }

// Independent material points; no shared state and no parallel reduction.
// Input columns: E, fy, Hiso, Hkin, yield tolerance; ep, alpha, q, energy.
extern "C" int sa_steel_batch_v1(
    std::size_t count, const double* strains, const double* materials,
    const double* parents, int workers, double* outputs,
    std::size_t* bad_index) noexcept {
  last_workers = 0;
  if (bad_index == nullptr) return 1;
  if (count == 0 || count > 1000000 || strains == nullptr ||
      materials == nullptr || parents == nullptr || outputs == nullptr ||
      workers < 1 || workers > 256) return 1;
  if (reinterpret_cast<std::uintptr_t>(bad_index) % alignof(std::size_t) != 0 ||
      reinterpret_cast<std::uintptr_t>(strains) % alignof(double) != 0 ||
      reinterpret_cast<std::uintptr_t>(materials) % alignof(double) != 0 ||
      reinterpret_cast<std::uintptr_t>(parents) % alignof(double) != 0 ||
      reinterpret_cast<std::uintptr_t>(outputs) % alignof(double) != 0) return 1;
  const auto overlaps = [](const void* a, std::size_t na,
                           const void* b, std::size_t nb) {
    const auto x = reinterpret_cast<std::uintptr_t>(a);
    const auto y = reinterpret_cast<std::uintptr_t>(b);
    const auto maximum = std::numeric_limits<std::uintptr_t>::max();
    return x > maximum - na || y > maximum - nb ||
        (x < y + nb && y < x + na);
  };
  const std::size_t bytes = count * sizeof(double);
  if (overlaps(outputs, 11 * bytes, strains, bytes) ||
      overlaps(outputs, 11 * bytes, materials, 5 * bytes) ||
      overlaps(outputs, 11 * bytes, parents, 4 * bytes) ||
      overlaps(bad_index, sizeof(*bad_index), outputs, 11 * bytes) ||
      overlaps(bad_index, sizeof(*bad_index), strains, bytes) ||
      overlaps(bad_index, sizeof(*bad_index), materials, 5 * bytes) ||
      overlaps(bad_index, sizeof(*bad_index), parents, 4 * bytes)) return 1;
  *bad_index = std::numeric_limits<std::size_t>::max();
  for (std::size_t i = 0; i < count; ++i) {
    const double* m = materials + 5 * i;
    const double* p = parents + 4 * i;
    bool valid = std::isfinite(strains[i]);
    for (int j = 0; j < 5; ++j) valid = valid && std::isfinite(m[j]);
    for (int j = 0; j < 4; ++j) valid = valid && std::isfinite(p[j]);
    const double tol = 1.0e-12 + 1.0e-12 *
        std::max({std::abs(p[0]), p[2], 1.0});
    const auto close = [](double a, double b) {
      return std::isfinite(a) && std::isfinite(b) && std::abs(a - b) <=
          std::max(1.0e-12, 1.0e-12 * std::max(std::abs(a), std::abs(b)));
    };
    valid = valid && m[0] > 0.0 && m[1] > 0.0 && m[2] >= 0.0 &&
        m[3] >= 0.0 && m[4] >= 0.0 && p[2] >= 0.0 && p[3] >= 0.0 &&
        std::abs(p[0]) <= p[2] + tol && close(p[1], m[3] * p[0]) &&
        close(p[3], m[1] * p[2]);
    if (!valid) { *bad_index = i; return 2; }
  }
  int observed_workers = 1;
  #pragma omp parallel for schedule(static) num_threads(workers) if(workers > 1)
  for (std::size_t i = 0; i < count; ++i) {
    if (i == 0) observed_workers = omp_get_num_threads();
    const double* m = materials + 5 * i;
    const double* p = parents + 4 * i;
    double* o = outputs + 11 * i;
    const double trial_stress = m[0] * (strains[i] - p[0]);
    const double relative = trial_stress - p[1];
    const double trial_yield = std::abs(relative) - (m[1] + m[2] * p[2]);
    std::copy(p, p + 4, o + 6);
    o[0] = trial_stress;
    o[1] = m[0];
    o[3] = 0.0;
    o[10] = 0.0;
    if (trial_yield > m[4]) {
      const double direction = relative >= 0.0 ? 1.0 : -1.0;
      const double hardening = m[2] + m[3];
      const double increment = trial_yield / (m[0] + hardening);
      o[6] = p[0] + increment * direction;
      o[7] = p[1] + m[3] * increment * direction;
      o[8] = p[2] + increment;
      o[9] = p[3] + m[1] * increment;
      o[0] = trial_stress - m[0] * increment * direction;
      o[1] = m[0] * hardening / (m[0] + hardening);
      o[3] = increment;
      o[10] = 1.0;
    }
    o[2] = strains[i] - o[6];
    o[4] = trial_yield;
    o[5] = std::abs(o[0] - o[7]) - (m[1] + m[2] * o[8]);
  }
  last_workers = observed_workers;
  for (std::size_t i = 0; i < count; ++i) {
    for (int j = 0; j < 11; ++j) {
      if (!std::isfinite(outputs[11 * i + static_cast<std::size_t>(j)])) {
        *bad_index = i;
        return 3;
      }
    }
  }
  return 0;
}
