from __future__ import annotations

import pytest

from structural_analysis.materials.elastic import ElasticIsotropicMaterial


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"id": "M1", "elastic_modulus": float("nan"), "poisson_ratio": 0.3},
            "elastic modulus must be finite and positive",
        ),
        (
            {"id": "M1", "elastic_modulus": 200.0e6, "poisson_ratio": float("nan")},
            "Poisson ratio must be finite",
        ),
        (
            {
                "id": "M1",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
                "density": float("inf"),
            },
            "density must be finite and positive",
        ),
    ],
)
def test_non_finite_material_properties_are_rejected(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ElasticIsotropicMaterial.from_mapping(payload)


def test_valid_isotropic_material_derives_shear_modulus() -> None:
    material = ElasticIsotropicMaterial.from_mapping(
        {
            "id": "M1",
            "elastic_modulus": 200.0e6,
            "poisson_ratio": 0.3,
        }
    )

    assert material.shear_modulus == pytest.approx(200.0e6 / 2.6)
