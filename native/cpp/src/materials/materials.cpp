#include "materials.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace structural::materials {
namespace {

[[nodiscard]] bool finite_positive(const double value) {
    return std::isfinite(value) && value > 0.0;
}

}  // namespace

double ElasticIsotropic::shear_modulus_pa() const {
    validate();
    return youngs_modulus_pa / (2.0 * (1.0 + poisson_ratio));
}

void ElasticIsotropic::validate() const {
    if (!finite_positive(youngs_modulus_pa)) {
        throw std::invalid_argument("Young's modulus must be finite and positive");
    }
    if (!std::isfinite(poisson_ratio) || poisson_ratio <= -1.0 || poisson_ratio >= 0.5) {
        throw std::invalid_argument("Poisson ratio must be finite and lie in (-1, 0.5)");
    }
    if (!finite_positive(density_kg_per_m3)) {
        throw std::invalid_argument("density must be finite and positive");
    }
}

void BilinearUniaxialConfig::validate() const {
    if (!finite_positive(youngs_modulus_pa) || !finite_positive(yield_stress_pa)) {
        throw std::invalid_argument("bilinear modulus and yield stress must be finite and positive");
    }
    if (!std::isfinite(hardening_ratio) || hardening_ratio < 0.0 || hardening_ratio >= 1.0) {
        throw std::invalid_argument("bilinear hardening ratio must lie in [0, 1)");
    }
}

BilinearUniaxialPoint::BilinearUniaxialPoint(const BilinearUniaxialConfig config)
    : config_(config) {
    config_.validate();
}

BilinearUniaxialResponse BilinearUniaxialPoint::trial(
    const double strain,
    const std::uint64_t epoch) {
    if (!std::isfinite(strain)) {
        throw std::invalid_argument("trial strain must be finite");
    }
    if (committed_epoch_ == std::numeric_limits<std::uint64_t>::max()
        || epoch != committed_epoch_ + 1U) {
        throw std::logic_error("trial epoch must be the next committed epoch");
    }

    const auto elastic_trial =
        config_.youngs_modulus_pa * (strain - committed_plastic_strain_);
    const auto hardening_modulus = config_.hardening_ratio == 0.0
        ? 0.0
        : config_.youngs_modulus_pa * config_.hardening_ratio
            / (1.0 - config_.hardening_ratio);
    const auto current_yield = config_.yield_stress_pa
        + hardening_modulus * committed_accumulated_plastic_strain_;
    const auto yield_function = std::abs(elastic_trial) - current_yield;

    auto response = BilinearUniaxialResponse {
        strain,
        elastic_trial,
        config_.youngs_modulus_pa,
        committed_plastic_strain_,
        committed_accumulated_plastic_strain_,
        false,
        epoch,
    };
    if (yield_function > 0.0) {
        const auto sign = std::copysign(1.0, elastic_trial);
        const auto plastic_increment =
            yield_function / (config_.youngs_modulus_pa + hardening_modulus);
        response.plastic_strain += sign * plastic_increment;
        response.accumulated_plastic_strain += plastic_increment;
        response.stress_pa = config_.youngs_modulus_pa * (strain - response.plastic_strain);
        response.tangent_pa = config_.hardening_ratio * config_.youngs_modulus_pa;
        response.yielded = true;
    }
    if (!std::isfinite(response.stress_pa) || !std::isfinite(response.tangent_pa)
        || !std::isfinite(response.plastic_strain)
        || !std::isfinite(response.accumulated_plastic_strain)) {
        throw std::invalid_argument("bilinear trial exceeds the finite numerical domain");
    }
    trial_ = response;
    has_trial_ = true;
    return response;
}

void BilinearUniaxialPoint::commit(const std::uint64_t epoch) {
    if (!has_trial_ || trial_.epoch != epoch || epoch != committed_epoch_ + 1U) {
        throw std::logic_error("commit requires the active next-epoch trial");
    }
    committed_plastic_strain_ = trial_.plastic_strain;
    committed_accumulated_plastic_strain_ = trial_.accumulated_plastic_strain;
    committed_epoch_ = epoch;
    has_trial_ = false;
}

void BilinearUniaxialPoint::rollback(const std::uint64_t epoch) {
    if (!has_trial_ || trial_.epoch != epoch || epoch != committed_epoch_ + 1U) {
        throw std::logic_error("rollback requires the active next-epoch trial");
    }
    has_trial_ = false;
}

std::uint64_t BilinearUniaxialPoint::committed_epoch() const noexcept {
    return committed_epoch_;
}

bool BilinearUniaxialPoint::has_trial() const noexcept {
    return has_trial_;
}

double BilinearUniaxialPoint::committed_plastic_strain() const noexcept {
    return committed_plastic_strain_;
}

double BilinearUniaxialPoint::committed_accumulated_plastic_strain() const noexcept {
    return committed_accumulated_plastic_strain_;
}

}  // namespace structural::materials
