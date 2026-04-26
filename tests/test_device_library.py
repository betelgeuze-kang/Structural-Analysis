from __future__ import annotations

from implementation.phase1.device_library import (
    FrictionPendulumBearing,
    LeadRubberBearing,
    TunedMassDamper,
    ViscoelasticDamper,
    ViscousDamper,
    build_default_device_library,
    describe_device_library,
    describe_device_support_surface,
)


def test_device_library_exposes_expected_devices() -> None:
    library = build_default_device_library()
    assert sorted(library) == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]


def test_device_library_switches_expected_states() -> None:
    viscous = ViscousDamper(damping_coefficient=100.0, exponent=1.0)
    viscoelastic = ViscoelasticDamper(stiffness=500.0, damping_coefficient=25.0)
    pendulum = FrictionPendulumBearing(radius_m=2.0, friction_coefficient=0.1, vertical_load=100.0)
    lrb = LeadRubberBearing(elastic_stiffness=1000.0, yield_force=10.0, post_yield_ratio=0.2)
    tmd = TunedMassDamper(stiffness=300.0, damping=20.0, mass=50.0)

    assert viscous.evaluate(0.0, velocity=0.2).state_label == "dissipating"
    assert viscoelastic.evaluate(0.02, velocity=0.1).state_label == "viscoelastic"
    assert pendulum.evaluate(0.01).state_label == "stick"
    assert pendulum.evaluate(0.5).state_label == "slide"
    assert lrb.evaluate(0.005).state_label == "elastic"
    assert lrb.evaluate(0.03).state_label == "yielded"
    assert tmd.evaluate(0.01, velocity=0.2).state_label == "tracking"


def test_device_library_rows_expose_family_and_contact_integration_surface() -> None:
    catalog = describe_device_library()

    assert catalog["viscous_damper"]["device_family"] == "damper"
    assert catalog["friction_pendulum"]["contact_integration_surface"] == "node_to_surface_proxy"
    assert catalog["lead_rubber_bearing"]["contact_proxy_ready"] is True
    assert catalog["tmd"]["search_ready_signature"] == "tuned_mass:tuned_mass_attachment_search:secondary_mass_attachment"
    assert catalog["viscoelastic_damper"]["sample_probe_energy_like"] > 0.0


def test_device_support_surface_summarizes_search_ready_and_proxy_devices() -> None:
    surface = describe_device_support_surface()

    assert surface["device_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]
    assert surface["support_search_model_types"] == surface["device_model_types"]
    assert surface["node_to_surface_proxy_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
    ]
    assert surface["device_family_counts"] == {
        "damper": 2,
        "isolation_bearing": 2,
        "tuned_mass": 1,
    }
    assert surface["contact_integration_surface_counts"] == {
        "brace_end_support_link": 2,
        "node_to_surface_proxy": 2,
        "secondary_mass_attachment": 1,
    }
    assert surface["support_depth_score"] == 10
    assert surface["support_search_surface_pass"] is True
    assert surface["node_to_surface_proxy_pass"] is True
    assert "support_search=5" in str(surface["summary_line"])
    assert "node_surface_proxy=2" in str(surface["summary_line"])
