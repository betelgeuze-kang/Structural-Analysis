"""Production material contracts used by authoritative solver paths."""

from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
    BilinearLinkResponse,
    BilinearLinkState,
    finite_difference_link_tangent_check,
    integrate_link_deformation_history,
)
from structural_analysis.materials.concrete_damage import (
    DAMAGE_ALGORITHM,
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
    finite_difference_concrete_damage_tangent_check,
    integrate_concrete_damage_history,
)
from structural_analysis.materials.composite_section import (
    COMPOSITE_ALGORITHM,
    ParallelCompositeSectionResponse,
    ParallelCompositeSectionState,
    ParallelSteelConcreteSectionMaterial,
    finite_difference_composite_section_tangent_check,
    integrate_composite_section_history,
)
from structural_analysis.materials.elastic import ElasticIsotropicMaterial
from structural_analysis.materials.uniaxial_plasticity import (
    RETURN_MAPPING_ALGORITHM,
    STATE_SCHEMA_VERSION,
    TANGENT_DEFINITION,
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
    finite_difference_consistent_tangent_check,
    integrate_strain_history,
)

__all__ = [
    "BilinearCombinedHardeningSteel",
    "BilinearCombinedHardeningLink",
    "BilinearLinkResponse",
    "BilinearLinkState",
    "AsymmetricConcreteDamageMaterial",
    "ConcreteDamageResponse",
    "ConcreteDamageState",
    "COMPOSITE_ALGORITHM",
    "DAMAGE_ALGORITHM",
    "ElasticIsotropicMaterial",
    "ParallelCompositeSectionResponse",
    "ParallelCompositeSectionState",
    "ParallelSteelConcreteSectionMaterial",
    "RETURN_MAPPING_ALGORITHM",
    "STATE_SCHEMA_VERSION",
    "TANGENT_DEFINITION",
    "UniaxialPlasticityResponse",
    "UniaxialPlasticityState",
    "finite_difference_consistent_tangent_check",
    "finite_difference_concrete_damage_tangent_check",
    "finite_difference_composite_section_tangent_check",
    "finite_difference_link_tangent_check",
    "integrate_composite_section_history",
    "integrate_link_deformation_history",
    "integrate_concrete_damage_history",
    "integrate_strain_history",
]
