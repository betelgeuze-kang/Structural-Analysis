#ifndef STRUCTURAL_MODEL_IR_SHA256_HPP
#define STRUCTURAL_MODEL_IR_SHA256_HPP

#include <string>
#include <string_view>

namespace structural::model_ir {

[[nodiscard]] std::string sha256_hex(std::string_view input);

} // namespace structural::model_ir

#endif
