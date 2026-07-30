"""Production material contracts used by authoritative solver paths."""

from structural_analysis.materials.admissibility import (
    MaterialAdmissibility,
    MaterialPathNotAdmissibleError,
    ScalarLoadingPathDemand,
    require_scalar_loading_path_admissible,
    scalar_loading_path_demand,
)
from structural_analysis.materials.elastic import ElasticIsotropicMaterial

__all__ = [
    "ElasticIsotropicMaterial",
    "MaterialAdmissibility",
    "MaterialPathNotAdmissibleError",
    "ScalarLoadingPathDemand",
    "require_scalar_loading_path_admissible",
    "scalar_loading_path_demand",
]
