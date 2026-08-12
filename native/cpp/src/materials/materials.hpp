#ifndef STRUCTURAL_MATERIALS_MATERIALS_HPP
#define STRUCTURAL_MATERIALS_MATERIALS_HPP

#include <cstdint>

namespace structural::materials {

struct ElasticIsotropic {
    double youngs_modulus_pa;
    double poisson_ratio;
    double density_kg_per_m3;

    [[nodiscard]] double shear_modulus_pa() const;
    void validate() const;
};

struct BilinearUniaxialConfig {
    double youngs_modulus_pa;
    double yield_stress_pa;
    double hardening_ratio;

    void validate() const;
};

struct BilinearUniaxialResponse {
    double strain;
    double stress_pa;
    double tangent_pa;
    double plastic_strain;
    double accumulated_plastic_strain;
    bool yielded;
    std::uint64_t epoch;
};

class BilinearUniaxialPoint final {
  public:
    explicit BilinearUniaxialPoint(BilinearUniaxialConfig config);

    [[nodiscard]] BilinearUniaxialResponse trial(double strain, std::uint64_t epoch);
    void commit(std::uint64_t epoch);
    void rollback(std::uint64_t epoch);

    [[nodiscard]] std::uint64_t committed_epoch() const noexcept;
    [[nodiscard]] bool has_trial() const noexcept;
    [[nodiscard]] double committed_plastic_strain() const noexcept;
    [[nodiscard]] double committed_accumulated_plastic_strain() const noexcept;

  private:
    BilinearUniaxialConfig config_;
    std::uint64_t committed_epoch_ {0U};
    bool has_trial_ {false};
    BilinearUniaxialResponse trial_ {};
    double committed_plastic_strain_ {0.0};
    double committed_accumulated_plastic_strain_ {0.0};
};

}  // namespace structural::materials

#endif
