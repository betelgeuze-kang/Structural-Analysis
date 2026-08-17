#ifndef STRUCTURAL_ENGINE_INTERNAL_HPP
#define STRUCTURAL_ENGINE_INTERNAL_HPP

namespace structural_engine_internal {

void set_thread_error(const char *message) noexcept;
const char *thread_error() noexcept;

}  // namespace structural_engine_internal

#endif  // STRUCTURAL_ENGINE_INTERNAL_HPP
