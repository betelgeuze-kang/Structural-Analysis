#ifndef STRUCTURAL_MODEL_IR_INTERNAL_HPP
#define STRUCTURAL_MODEL_IR_INTERNAL_HPP

#include "structural/abi_v1.h"

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string_view>

namespace structural::model_ir {

struct NdthaAdapterProperties final {
    std::uint64_t element_index {};
    std::uint64_t load_pattern_index {};
    double story_height_m {};
    double youngs_modulus_pa {};
    double section_area_m2 {};
    double section_iy_m4 {};
    double story_stiffness_n_per_m {};
    double story_mass_kg {};
    double story_damping_n_s_per_m {};
    double floor_load_base_n {};
};

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
    [[nodiscard]] NdthaAdapterProperties adapt_fixed_guided_frame3d_x(
        std::string_view element_id,
        std::string_view base_node_id,
        std::string_view floor_node_id,
        std::string_view load_pattern_id,
        double damping_ratio) const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace structural::model_ir

#endif
