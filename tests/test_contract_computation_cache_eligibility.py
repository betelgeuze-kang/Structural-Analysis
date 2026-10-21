"""Schema success may be reused only by unchanged, registered pure validators."""

import gc
import importlib.util
import weakref

from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators
import pytest
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from structural_analysis.engine_v2.contracts import _computation_cache as cache
from structural_analysis.engine_v2.contracts import equation_scaling, execution_plan


def pure(schema):
    validator = execution_plan._StrictDraft202012Validator(schema)
    assert cache._register_pure_schema_validator(validator)
    return validator


def test_source_factories_register_their_actual_instances():
    candidates = (
        execution_plan._execution_plan_validator(),
        equation_scaling._equation_scaling_validator(),
        equation_scaling._scaled_residual_trace_validator(),
    )
    assert all(
        cache._registered_schema_key(validator) is not None for validator in candidates
    )


def test_only_registered_same_instance_success_is_reused_within_one_scope():
    validator = pure({"type": "integer"})
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        memo = cache._SCHEMA_MEMO.get()
        assert len(memo.successes) == 1
        key = next(iter(memo.successes))
        sentinel = object()
        memo.successes[key] = sentinel
        assert cache.schema_errors(validator, 1) == []
        # A hit does not replace the existing admission record with a new success.
        assert memo.successes[key] is sentinel
    with cache.reuse_contract_computations():
        assert not cache._SCHEMA_MEMO.get().successes


def test_custom_keyword_closure_is_never_registered_or_memoized():
    state = {"allow": True, "calls": 0}

    def gate(validator, expected, instance, schema):
        state["calls"] += 1
        if not state["allow"]:
            yield ValidationError("custom gate closed")

    custom = validators.extend(Draft202012Validator, {"gate": gate})({"gate": True})
    assert not cache._register_pure_schema_validator(custom)
    with cache.reuse_contract_computations():
        assert cache.schema_errors(custom, 1) == []
        state["allow"] = False
        assert cache.schema_errors(custom, 1)[0].message == "custom gate closed"
        assert not cache._SCHEMA_MEMO.get().successes
    assert state["calls"] == 2


def test_unhashable_custom_keyword_callable_keeps_the_original_validation_path():
    class Gate:
        __hash__ = None
        allow = True

        def __call__(self, validator, expected, instance, schema):
            if not self.allow:
                yield ValidationError("unhashable gate closed")

    gate = Gate()
    custom = validators.extend(Draft202012Validator, {"gate": gate})({"gate": True})
    assert not cache._register_pure_schema_validator(custom)
    with cache.reuse_contract_computations():
        assert cache.schema_errors(custom, 1) == []
        gate.allow = False
        assert cache.schema_errors(custom, 1)[0].message == "unhashable gate closed"


def test_custom_keyword_on_the_known_class_is_rejected_at_registration(monkeypatch):
    cls = execution_plan._StrictDraft202012Validator

    def stateful(*args):
        yield ValidationError("customized known class")

    monkeypatch.setattr(cls, "VALIDATORS", {**cls.VALIDATORS, "type": stateful})
    validator = cls({"type": "integer"})
    assert not cache._register_pure_schema_validator(validator)
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1)[0].message == "customized known class"


def test_mutated_instance_validators_cannot_borrow_its_earlier_success():
    validator = pure({"type": "integer"})
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        validator._validators = [(validator.VALIDATORS["type"], "type", "string")]
        assert cache.schema_errors(validator, 1)
        assert cache._registered_schema_key(validator) is None


def test_same_class_unregistered_other_instance_cannot_borrow_success():
    first = pure({"type": "integer"})
    second = type(first)({"type": "integer"})
    second._validators = [(second.VALIDATORS["type"], "type", "string")]
    with cache.reuse_contract_computations():
        assert cache.schema_errors(first, 1) == []
        assert cache.schema_errors(second, 1)
        assert len(cache._SCHEMA_MEMO.get().successes) == 1


def test_schema_changes_fall_back_without_adding_a_new_admission():
    validator = pure({"type": "integer"})
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        validator.schema["type"] = "string"
        assert cache._registered_schema_key(validator) is None
        assert cache.schema_errors(validator, 1) == list(validator.iter_errors(1))
        assert len(cache._SCHEMA_MEMO.get().successes) == 1


def test_resolver_drift_cannot_reuse_a_local_reference_success():
    schema = {"$defs": {"value": {"type": "integer"}}, "$ref": "#/$defs/value"}
    validator = pure(schema)
    other = {"$defs": {"value": {"type": "string"}}}
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        validator._resolver = cache._DEFAULT_REGISTRY.resolver_with_root(
            DRAFT202012.create_resource(other)
        )
        assert cache.schema_errors(validator, 1)
        assert cache._registered_schema_key(validator) is None


def test_custom_registry_and_resolver_are_rejected_before_registration():
    cls = execution_plan._StrictDraft202012Validator
    custom_registry = cls({"type": "integer"}, registry=Registry())
    assert not cache._register_pure_schema_validator(custom_registry)
    custom_resolver = cache._DEFAULT_REGISTRY.resolver_with_root(
        DRAFT202012.create_resource({"type": "string"})
    )
    custom = cls({"type": "integer"}, _resolver=custom_resolver)
    assert not cache._register_pure_schema_validator(custom)


def test_format_checker_drift_runs_its_new_failure():
    validator = pure({"type": "string", "format": "ipv4"})
    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, "not-an-ip") == []
        validator.format_checker = FormatChecker()
        assert cache.schema_errors(validator, "not-an-ip")
        assert cache._registered_schema_key(validator) is None


@pytest.mark.parametrize("name", ["iter_errors", "descend", "is_type", "evolve"])
def test_changed_validator_methods_are_executed_instead_of_reused(monkeypatch, name):
    validator = pure({"type": "object", "properties": {"x": {"type": "integer"}}})
    cls = type(validator)
    original = getattr(cls, name)
    calls = []

    def changed(*args, **kwargs):
        calls.append(name)
        return original(*args, **kwargs)

    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, {"x": 1}) == []
        monkeypatch.setattr(cls, name, changed)
        assert cache.schema_errors(validator, {"x": 1}) == []
        assert calls
        assert len(cache._SCHEMA_MEMO.get().successes) == 1


def test_same_function_changed_code_is_not_an_identity_cache_hit(monkeypatch):
    validator = pure({"type": "integer"})

    def reject(self, instance, name):
        return False

    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        monkeypatch.setattr(type(validator).is_type, "__code__", reject.__code__)
        assert cache.schema_errors(validator, 1)


def test_type_checker_callback_code_drift_is_not_an_identity_cache_hit(monkeypatch):
    validator = pure({"type": "integer"})
    callback = validator.TYPE_CHECKER._type_checkers["integer"]

    def reject(checker, instance):
        return False

    with cache.reuse_contract_computations():
        assert cache.schema_errors(validator, 1) == []
        monkeypatch.setattr(callback, "__code__", reject.__code__)
        assert cache.schema_errors(validator, 1)


def test_weak_registration_does_not_retain_the_validator_or_recycle_its_id():
    validator = pure({"type": "integer"})
    identity, reference = id(validator), weakref.ref(validator)
    assert identity in cache._PURE_SCHEMA_VALIDATORS
    del validator
    gc.collect()
    assert reference() is None
    assert identity not in cache._PURE_SCHEMA_VALIDATORS


@pytest.mark.parametrize(
    "schema", [{"$ref": "urn:external"}, {"$dynamicRef": "urn:external"}]
)
def test_external_reference_validators_are_never_registered(schema):
    validator = execution_plan._StrictDraft202012Validator(schema)
    assert not cache._register_pure_schema_validator(validator)


@pytest.mark.parametrize(
    "unsupported", ["missing_registry", "non_function_method", "large_private_closure"]
)
def test_unsupported_private_introspection_disables_reuse_without_breaking_import(
    monkeypatch, unsupported
):
    validator = execution_plan._StrictDraft202012Validator({"type": "integer"})
    if unsupported == "missing_registry":
        monkeypatch.setattr(Draft202012Validator, "__attrs_attrs__", ())
    elif unsupported == "non_function_method":
        monkeypatch.setattr(Draft202012Validator, "iter_errors", object())
    else:
        method = Draft202012Validator.evolve
        cell = method.__closure__[method.__code__.co_freevars.index("evolve_fields")]
        monkeypatch.setattr(cell, "cell_contents", [("unused", "unused")] * 100)
    # Load an isolated alias: existing imported function bindings and factory
    # registrations are not replaced or reset for the rest of this test run.
    spec = importlib.util.spec_from_file_location(
        "structural_analysis.engine_v2.contracts._unsupported_cache_probe",
        cache.__file__,
    )
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe._PURE_SCHEMA_ELIGIBILITY_AVAILABLE is False
    assert not probe._register_pure_schema_validator(validator)
    with probe.reuse_contract_computations():
        assert probe.schema_errors(validator, 1) == []
        assert probe.schema_errors(validator, "bad")
        assert not probe._SCHEMA_MEMO.get().successes
