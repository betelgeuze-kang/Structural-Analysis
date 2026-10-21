"""Pure contract-cache regressions; no solver or material trial execution."""

from copy import copy, deepcopy
from dataclasses import asdict, dataclass, field, replace
import gc
import weakref

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts import _canonical
from structural_analysis.materials import stateful_fiber_section as module
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulSectionFiber,
    make_rectangular_stateful_rc_fiber_section,
)


def legacy_payload(section):
    """Independent pre-cache payload, including its original copying behavior."""
    return {
        "schema_version": module.STATEFUL_FIBER_SECTION_SCHEMA_VERSION,
        "section_id": section.section_id,
        "strain_relation": module.FIBER_SECTION_STRAIN_RELATION,
        "resultant_definition": module.FIBER_SECTION_RESULTANT_DEFINITION,
        "tangent_definition": module.FIBER_SECTION_TANGENT_DEFINITION,
        "fibers": [fiber.to_dict() for fiber in section.fibers],
        "steel": asdict(section.steel),
        "concrete": asdict(section.concrete),
        **(
            {
                "steel_overrides": [
                    {"fiber_id": fiber_id, "material": asdict(material)}
                    for fiber_id, material in section.steel_overrides
                ]
            }
            if section.steel_overrides
            else {}
        ),
    }


def legacy_hash(section):
    return canonical_hash(legacy_payload(section))


@pytest.fixture(autouse=True)
def clear_contract_cache():
    module._cached_section_contract_hash.cache_clear()
    yield
    module._cached_section_contract_hash.cache_clear()


def test_legacy_hash_and_empty_override_omission_are_exact():
    section = make_rectangular_stateful_rc_fiber_section()
    expected = "sha256:dd63b15b8a78e6080b9839e629cec511d2802f2980dccdbb7042788e4a468f39"
    assert "steel_overrides" not in legacy_payload(section)
    assert section.contract_hash == legacy_hash(section) == expected
    assert section.contract_hash == expected
    assert module._cached_section_contract_hash.cache_info().hits == 1


def test_equal_replaced_shallow_and_deep_copies_share_only_value_cache():
    section = make_rectangular_stateful_rc_fiber_section()
    copies = (section, copy(section), deepcopy(section), replace(section))
    for candidate in copies:
        assert candidate.contract_hash == legacy_hash(candidate)
    info = module._cached_section_contract_hash.cache_info()
    assert (info.misses, info.hits, info.currsize, info.maxsize) == (1, 3, 1, 128)


@pytest.mark.parametrize(
    "owner,name,value",
    [
        ("section", "section_id", "other-section"),
        ("fiber", "fiber_id", "other-concrete-fiber"),
        ("fiber", "y_m", 0.125),
        ("fiber", "area_m2", 0.021),
        ("fiber", "material_kind", "steel"),
        ("steel", "elastic_modulus_mpa", 195000.0),
        ("steel", "yield_stress_mpa", 270.0),
        ("steel", "isotropic_hardening_modulus_mpa", 2500.0),
        ("steel", "kinematic_hardening_modulus_mpa", 4500.0),
        ("steel", "yield_tolerance_mpa", 2.0e-10),
        ("steel", "material_id", "other-steel"),
        ("concrete", "elastic_modulus_mpa", 28000.0),
        ("concrete", "tensile_strength_mpa", 2.5),
        ("concrete", "compressive_strength_mpa", 28.0),
        ("concrete", "tensile_softening_rate", 2500.0),
        ("concrete", "compressive_softening_rate", 350.0),
        ("concrete", "history_tolerance", 2.0e-14),
        ("concrete", "material_id", "other-concrete"),
    ],
)
def test_each_declared_physical_field_changes_the_warm_key(owner, name, value):
    section = make_rectangular_stateful_rc_fiber_section()
    original = section.contract_hash
    if owner == "section":
        changed = replace(section, **{name: value})
    elif owner == "fiber":
        changed = replace(
            section,
            fibers=(replace(section.fibers[0], **{name: value}), *section.fibers[1:]),
        )
    else:
        changed = replace(
            section, **{owner: replace(getattr(section, owner), **{name: value})}
        )
    assert changed.contract_hash == legacy_hash(changed)
    assert changed.contract_hash != original
    assert section.contract_hash == original


def test_fiber_order_and_override_values_are_preserved():
    section = make_rectangular_stateful_rc_fiber_section()
    original = section.contract_hash
    reversed_fibers = replace(section, fibers=section.fibers[::-1])
    assert reversed_fibers.contract_hash == legacy_hash(reversed_fibers) != original
    steel_ids = [
        fiber.fiber_id for fiber in section.fibers if fiber.material_kind == "steel"
    ]
    law = replace(section.steel, yield_stress_mpa=125.0)
    rows = ((steel_ids[0], law), (steel_ids[1], section.steel))
    first = replace(section, steel_overrides=rows)
    reordered = replace(section, steel_overrides=rows[::-1])
    assert first.contract_hash == reordered.contract_hash == legacy_hash(first)
    changed = replace(first, steel_overrides=((steel_ids[0], section.steel),))
    assert changed.contract_hash == legacy_hash(changed) != first.contract_hash
    # An explicitly declared assignment is present even when its law is default.
    assert changed.contract_hash != original


def test_current_values_are_reread_after_same_object_tampering():
    section = make_rectangular_stateful_rc_fiber_section()
    parent = section.initial_state()
    original = section.contract_hash
    object.__setattr__(section.steel, "yield_stress_mpa", 300.0)
    changed = section.contract_hash
    assert changed == legacy_hash(section) != original
    with pytest.raises(ValueError, match="section_contract_hash"):
        section.validate_state(parent)
    object.__setattr__(section.steel, "yield_stress_mpa", 250.0)
    assert section.contract_hash == original


def test_python_equal_boolean_integer_and_float_have_distinct_cache_keys():
    section = make_rectangular_stateful_rc_fiber_section()
    hashes = []
    for value in (True, 1, 1.0):
        # All three currently pass this material's material_id truthiness check.
        candidate = replace(
            section, concrete=AsymmetricConcreteDamageMaterial(material_id=value)
        )
        hashes.append(candidate.contract_hash)
        assert candidate.contract_hash == legacy_hash(candidate)
    assert len(set(hashes)) == 3
    assert module._cached_section_contract_hash.cache_info().misses == 3


def test_python_equal_type_tampering_cannot_reuse_an_old_digest():
    section = make_rectangular_stateful_rc_fiber_section()
    original = section.contract_hash
    object.__setattr__(section.concrete, "elastic_modulus_mpa", 30000)
    assert section.contract_hash == legacy_hash(section) != original
    object.__setattr__(section.concrete, "material_id", 1)
    first = section.contract_hash
    object.__setattr__(section.concrete, "material_id", 1.0)
    assert section.contract_hash == legacy_hash(section) != first


def test_signed_floating_zero_keeps_canonical_hash_and_warm_key():
    section = make_rectangular_stateful_rc_fiber_section()
    object.__setattr__(section.fibers[0], "y_m", 0.0)
    original = section.contract_hash
    object.__setattr__(section.fibers[0], "y_m", -0.0)
    assert section.contract_hash == legacy_hash(section) == original
    assert module._cached_section_contract_hash.cache_info().hits == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("characteristic_length_m", 0.02),
        ("tensile_fracture_energy_n_per_m", 150.0),
        ("compressive_fracture_energy_n_per_m", 25000.0),
    ],
)
def test_fracture_energy_subclass_additional_fields_are_included(name, value):
    section = replace(
        make_rectangular_stateful_rc_fiber_section(),
        concrete=FractureEnergyConcreteDamageMaterial(),
    )
    original = section.contract_hash
    changed = replace(section, concrete=replace(section.concrete, **{name: value}))
    assert original == legacy_hash(section)
    assert changed.contract_hash == legacy_hash(changed) != original


@dataclass(frozen=True)
class AnnotatedConcrete(AsymmetricConcreteDamageMaterial):
    annotation: dict = field(
        default_factory=lambda: {"values": [True, 1, 1.0], "tag": (None, "x")}
    )


def test_unhashable_subclass_fields_are_snapshotted_recursively_and_freshly():
    section = replace(
        make_rectangular_stateful_rc_fiber_section(), concrete=AnnotatedConcrete()
    )
    original = section.contract_hash
    assert original == legacy_hash(section)
    section.concrete.annotation["values"][0] = 1
    assert section.contract_hash == legacy_hash(section) != original
    assert module._cached_section_contract_hash.cache_info().currsize == 2


@dataclass(frozen=True)
class CustomFiber(StatefulSectionFiber):
    def to_dict(self):
        return {**super().to_dict(), "custom_dispatch": "preserved"}


def test_custom_fiber_to_dict_dispatch_uses_the_legacy_uncached_path():
    section = make_rectangular_stateful_rc_fiber_section()
    fiber = CustomFiber(**asdict(section.fibers[0]))
    section = replace(section, fibers=(fiber, *section.fibers[1:]))
    assert section.contract_hash == legacy_hash(section)
    assert module._cached_section_contract_hash.cache_info().currsize == 0


class CopiedString(str):
    def __deepcopy__(self, memo):
        return "copy-semantics-preserved"


def test_custom_scalar_copy_semantics_and_numpy_scalar_use_legacy_fallback():
    section = make_rectangular_stateful_rc_fiber_section()
    for value in (CopiedString("original-value"), np.int64(1)):
        object.__setattr__(section.concrete, "material_id", value)
        assert section.contract_hash == legacy_hash(section)
    assert module._cached_section_contract_hash.cache_info().currsize == 0


@pytest.mark.parametrize("owner", ["steel", "concrete"])
def test_non_dataclass_material_root_keeps_legacy_rejection(owner):
    section = replace(make_rectangular_stateful_rc_fiber_section(), **{owner: {"x": 1}})
    with pytest.raises(TypeError) as expected:
        legacy_hash(section)
    with pytest.raises(type(expected.value)) as actual:
        _ = section.contract_hash
    assert str(actual.value) == str(expected.value)


@pytest.mark.parametrize(
    "owner,name", [("fiber", "y_m"), ("concrete", "elastic_modulus_mpa")]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_tampering_after_warm_cache_keeps_error_type_and_path(
    owner, name, value
):
    section = make_rectangular_stateful_rc_fiber_section()
    _ = section.contract_hash
    target = section.fibers[0] if owner == "fiber" else section.concrete
    object.__setattr__(target, name, value)
    with pytest.raises(CanonicalContractError) as expected:
        legacy_hash(section)
    with pytest.raises(CanonicalContractError) as actual:
        _ = section.contract_hash
    assert str(actual.value) == str(expected.value)
    assert module._cached_section_contract_hash.cache_info().currsize == 1


def test_private_derived_attributes_do_not_enter_the_physical_key():
    section = make_rectangular_stateful_rc_fiber_section()
    original = section.contract_hash
    object.__setattr__(section, "_derived_contract_test", {"untrusted": object()})
    assert section.contract_hash == legacy_hash(section) == original
    assert module._cached_section_contract_hash.cache_info().hits == 1


def test_cache_is_entry_bounded_and_does_not_retain_model_objects():
    section = make_rectangular_stateful_rc_fiber_section()
    references = (
        weakref.ref(section),
        weakref.ref(section.concrete),
        weakref.ref(section.fibers[0]),
    )
    _ = section.contract_hash
    del section
    gc.collect()
    assert all(reference() is None for reference in references)
    for index in range(140):
        candidate = replace(
            make_rectangular_stateful_rc_fiber_section(), section_id=f"section-{index}"
        )
        assert candidate.contract_hash == legacy_hash(candidate)
    info = module._cached_section_contract_hash.cache_info()
    assert info.currsize == info.maxsize == 128


def test_normal_exact_dataclasses_use_direct_primitive_snapshot(monkeypatch):
    section = make_rectangular_stateful_rc_fiber_section()
    expected = legacy_hash(section)
    assert module._section_contract_snapshot(section)[0] == "plain_section"

    # Only the generic recursive walker is replaced; supported direct rows
    # must not pay for repeated dataclass/field dispatch on each scalar leaf.
    def forbidden(value):
        raise AssertionError("generic value walker was used")

    monkeypatch.setattr(module, "_section_contract_value_snapshot", forbidden)
    assert section.contract_hash == expected


def test_forced_type_changes_use_existing_typed_generic_snapshot():
    section = make_rectangular_stateful_rc_fiber_section()
    assert module._section_contract_snapshot(section)[0] == "plain_section"
    object.__setattr__(section.concrete, "material_id", True)
    assert module._section_contract_snapshot(section)[0] == "mapping"
    assert section.contract_hash == legacy_hash(section)


def test_instance_to_dict_shadow_cannot_reuse_a_warm_digest():
    section = make_rectangular_stateful_rc_fiber_section()
    before = section.contract_hash
    fiber = section.fibers[0]
    original = fiber.to_dict()
    object.__setattr__(fiber, "to_dict", lambda: {**original, "custom": True})
    assert section.contract_hash == legacy_hash(section) != before


@pytest.mark.parametrize(
    "change",
    [
        "to_dict",
        "to_dict_code",
        "asdict",
        "asdict_defaults",
        "canonical",
        "normalizer",
        "normalizer_code",
    ],
)
def test_warm_digest_respects_current_serialization_implementation(monkeypatch, change):
    section = make_rectangular_stateful_rc_fiber_section()
    before = section.contract_hash
    if change in ("to_dict", "to_dict_code"):

        def replacement(self):
            return {"changed": True}

        if change == "to_dict":
            monkeypatch.setattr(StatefulSectionFiber, "to_dict", replacement)
        else:
            monkeypatch.setattr(
                StatefulSectionFiber.to_dict, "__code__", replacement.__code__
            )
    elif change == "asdict":
        monkeypatch.setattr(module, "asdict", lambda value: {"changed": True})
    elif change == "asdict_defaults":

        def changed_factory(rows):
            return {**dict(rows), "changed": True}

        monkeypatch.setitem(asdict.__kwdefaults__, "dict_factory", changed_factory)
    elif change == "canonical":
        monkeypatch.setattr(module, "canonical_hash", lambda value: "changed-hash")
    elif change == "normalizer":
        monkeypatch.setattr(
            _canonical,
            "_normalize_json_value",
            lambda value, *, path: {"changed": True},
        )
    else:

        def replacement(value, *, path):
            return {"changed": True}

        monkeypatch.setattr(
            _canonical._normalize_json_value, "__code__", replacement.__code__
        )
    assert not module._section_contract_cache_eligible()
    payload = legacy_payload(section)
    if change == "asdict":
        # The legacy property's module-local alias is intentionally rebound;
        # this test module's independent imported alias remains unchanged.
        payload["steel"] = module.asdict(section.steel)
        payload["concrete"] = module.asdict(section.concrete)
    expected = module.canonical_hash(payload)
    assert section.contract_hash == expected != before
    assert module._cached_section_contract_hash.cache_info().hits == 0


def test_dataclass_layout_mutation_uses_current_generic_layout(monkeypatch):
    section = make_rectangular_stateful_rc_fiber_section()
    before = section.contract_hash
    # asdict observes current declared fields; remove a field after warming.
    changed_fields = dict(AsymmetricConcreteDamageMaterial.__dataclass_fields__)
    del changed_fields["material_id"]
    monkeypatch.setattr(
        AsymmetricConcreteDamageMaterial, "__dataclass_fields__", changed_fields
    )
    assert module._section_contract_snapshot(section)[0] == "mapping"
    assert section.contract_hash == legacy_hash(section) != before


def test_custom_dataclass_field_mapping_is_not_speculatively_observed(monkeypatch):
    class CustomFieldMapping(dict):
        def __len__(self):
            raise AssertionError("custom length was read")

        def items(self):
            raise AssertionError("custom items were read")

    section = make_rectangular_stateful_rc_fiber_section()
    monkeypatch.setattr(
        AsymmetricConcreteDamageMaterial,
        "__dataclass_fields__",
        CustomFieldMapping(AsymmetricConcreteDamageMaterial.__dataclass_fields__),
    )
    assert not module._section_plain_layouts_unchanged()
    assert module._plain_section_contract_snapshot(section) is None
    assert section.contract_hash == legacy_hash(section)


def test_hash_warming_keeps_stage1_implementation_guard_eligible():
    from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
        _AUDIT_IMPLEMENTATION,
    )

    assert _AUDIT_IMPLEMENTATION.unchanged()
    section = make_rectangular_stateful_rc_fiber_section()
    assert section.contract_hash == legacy_hash(section)
    assert section.contract_hash == legacy_hash(section)
    assert _AUDIT_IMPLEMENTATION.unchanged()
