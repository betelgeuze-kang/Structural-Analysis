#include "materials.hpp"

#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_near(
    const double actual,
    const double expected,
    const double tolerance,
    const std::string_view message) {
    expect(std::abs(actual - expected) <= tolerance, message);
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::exception&) {
        return;
    }
    expect(false, message);
}

}  // namespace

int main() {
    const structural::materials::ElasticIsotropic elastic {200.0E9, 0.25, 7850.0};
    elastic.validate();
    expect_near(elastic.shear_modulus_pa(), 80.0E9, 1.0E-5, "elastic shear modulus");
    expect_throws(
        [] { structural::materials::ElasticIsotropic {1.0, 0.5, 1.0}.validate(); },
        "invalid Poisson ratio must fail");

    structural::materials::BilinearUniaxialPoint point({200.0, 2.0, 0.1});
    const auto elastic_trial = point.trial(0.005, 1U);
    expect(!elastic_trial.yielded, "elastic trial must not yield");
    expect_near(elastic_trial.stress_pa, 1.0, 1.0E-15, "elastic trial stress");
    point.rollback(1U);
    expect(point.committed_epoch() == 0U, "rollback cannot advance the committed epoch");
    expect_near(point.committed_plastic_strain(), 0.0, 0.0, "rollback preserves plastic strain");

    const auto plastic_trial = point.trial(0.02, 1U);
    expect(plastic_trial.yielded, "plastic trial must yield");
    expect_near(plastic_trial.plastic_strain, 0.009, 1.0E-15, "return-map plastic strain");
    expect_near(plastic_trial.stress_pa, 2.2, 1.0E-14, "return-map stress");
    expect_near(plastic_trial.tangent_pa, 20.0, 1.0E-15, "consistent tangent");
    point.commit(1U);
    expect(point.committed_epoch() == 1U, "commit advances exactly one epoch");
    expect_near(point.committed_plastic_strain(), 0.009, 1.0E-15, "commit stores plastic strain");

    const auto unload_trial = point.trial(0.015, 2U);
    expect(!unload_trial.yielded, "bounded unload remains elastic");
    expect_near(unload_trial.stress_pa, 1.2, 1.0E-14, "unload stress uses committed state");
    expect_throws([&point] { point.commit(3U); }, "wrong commit epoch must fail");
    point.rollback(2U);
    expect_throws([&point] { static_cast<void>(point.trial(0.0, 4U)); }, "skipped epoch must fail");
    structural::materials::BilinearUniaxialPoint overflow_point(
        {std::numeric_limits<double>::max(), 1.0, 0.0});
    expect_throws(
        [&overflow_point] {
            static_cast<void>(overflow_point.trial(std::numeric_limits<double>::max(), 1U));
        },
        "non-finite trial response must fail before state publication");
    expect(!overflow_point.has_trial(), "failed trial cannot publish material state");
    return EXIT_SUCCESS;
}
