#ifndef STRUCTURAL_MODEL_IR_INTERNAL_HPP
#define STRUCTURAL_MODEL_IR_INTERNAL_HPP

#include "structural/abi_v1.h"

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string_view>

namespace structural::model_ir {

class Error final : public std::runtime_error {
public:
    Error(sa_status_code_v1 status, const char* message);

    [[nodiscard]] sa_status_code_v1 status() const noexcept;

private:
    sa_status_code_v1 status_;
};

class Model final {
public:
    explicit Model(const sa_model_ir_descriptor_v1& descriptor);
    ~Model();

    Model(const Model&) = delete;
    Model& operator=(const Model&) = delete;
    Model(Model&&) = delete;
    Model& operator=(Model&&) = delete;

    [[nodiscard]] std::string_view validation_report() const noexcept;
    [[nodiscard]] std::string_view snapshot() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace structural::model_ir

#endif
