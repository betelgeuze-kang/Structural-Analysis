# API Capability Support

Generated from artifacts/manifests/capabilities.yaml. Do not edit directly.

| Capability | Status | Public | Authority | Interfaces | Exact profile / boundary |
| --- | --- | --- | --- | --- | --- |
| Neutral canonical model | supported | yes | validated_input_contract | python_api, cli | structural-analysis-canonical-model.v1; Only schema-declared entities and units are accepted. |
| MIDAS MGT import | bounded_public | yes | input_translation_with_provenance | python_api, cli | topology_and_supported_property_subset; Unsupported records remain explicit; exact native round-trip is not closed. |
| IFC model-health import | bounded_public | yes | entity_scan_and_model_health_only | python_api, cli | ifc_step_model_health; Not a general analysis-ready IFC structural-model compiler. |
| Linear static analysis | bounded_public | yes | numerical_and_engineering_within_supported_elements | python_api, cli, workbench | cpu_dense_or_scipy_sparse_supported_frame_truss; No general shell, contact, staged-construction, or design-code authority. |
| Whole-model modal analysis | bounded_public | yes | numerical_within_explicit_frame_truss_mass_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense and no independent Level 2 comparison is promoted. |
| Whole-model linear buckling | bounded_public | yes | numerical_within_explicit_preload_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense and no independent Level 2 comparison is promoted. |
| Nonlinear two-bar truss | bounded_public | yes | bounded_material_geometric_newton | python_api, cli | symmetric_two_bar_material_geometric_v1; The profile does not generalize to arbitrary truss or frame topology. |
| Fixed-chord RC fiber frame | bounded_public | yes | exact_reaction_member_section_fiber_recovery | python_api, cli | planar_serial_cantilever_explicit_rectangular_rc.v1; Serial cantilever only; zero prescribed movement; dense CPU load control. |
| Corotational 2D fiber-frame assembly | experimental | no | bounded_assembly_candidate_no_public_api | internal_python | bounded_planar_stateful_corotational_fiber_frame2d.v1; Assembly-level candidate only; no unified public API, general member-feature contract, independent Level 2 verification, or release promotion. |
| OpenSees Level 2 verification | blocked | no | none | evidence | independent_operator_promotion_required; Fresh pinned technical comparisons pass narrowly, but independent operator attestation, legal review, broader nonlinear coverage, and a Level 2 promotion receipt are absent. |
| Second independent solver Level 2 verification | blocked | no | none | evidence | independent_operator_promotion_required; Fresh pinned CalculiX comparisons pass narrowly, but independent operator attestation, legal review, broader coverage, and a second-solver Level 2 promotion receipt are absent. |
| Cyclic corotational fiber-frame benchmarks | experimental | no | bounded_repository_benchmark_candidate | internal_python, evidence | two_member_planar_material_state_commit_rollback.v1; Repository-generated steel, concrete, composite, and link cases only; no published cyclic acceptance, 3D response, or release authority. |
| Workbench result and evidence review | bounded_public | yes | consumer_only | workbench | typed_workbench_case_and_evidence_reader; Workbench display and review decisions never create solver truth. |
| AI solver shadow control | shadow_only | no | proposal_and_evaluation_only | internal_python, evidence | deterministic_shadow_proposal_controller.v1; Shadow proposals are not executed and cannot alter solver truth. |
| Guarded AI execution | blocked | no | none | internal_python | independent_shadow_and_guard_receipts_required; No production action execution or autonomous engineering authority. |
| ROCm/HIP production backend | blocked | no | none | hardware_runner | performance_track_after_cpu_sparse_and_external_vv; Residency, full-path parity, fallback, and hardware provenance gates remain open. |

The Python API exposes the same registry through structural_analysis.api.capabilities(). The structural-analysis CLI prints it with --capabilities. Experimental, shadow-only, and blocked rows are discovery metadata, not executable public support.
