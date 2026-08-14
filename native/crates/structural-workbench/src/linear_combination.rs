use serde_json::{json, Value};

use super::WorkbenchError;

pub const MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1: usize = 2;
pub const MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1: usize = 64;
pub const MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1: usize = 8;
pub const MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1: usize = 64;

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ExpandedLinearLoadCombinationV1 {
    pub root_terms: Value,
    pub expanded_pattern_terms: Value,
    pub max_depth: usize,
    pub expanded_term_count: usize,
    pub nested: bool,
}

pub(crate) fn require_bounded_linear_load_combination(
    model: &Value,
    load_combination_id: &str,
) -> Result<ExpandedLinearLoadCombinationV1, WorkbenchError> {
    let patterns = model
        .get("load_patterns")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_snapshot_invalid",
                "verified ModelIR snapshot has no load-pattern array",
            )
        })?;
    if patterns
        .iter()
        .any(|pattern| pattern.get("id").and_then(Value::as_str) == Some(load_combination_id))
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_request_selector_ambiguous",
            format!("identity {load_combination_id} names both a load pattern and combination"),
        ));
    }
    let combinations = model
        .get("load_combinations")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_snapshot_invalid",
                "verified ModelIR snapshot has no load-combination array",
            )
        })?;
    let combination = find_combination(combinations, load_combination_id).ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_linear_combination_request_missing",
            format!("ModelIR has no load combination with identity {load_combination_id}"),
        )
    })?;
    require_linear_type(combination, load_combination_id)?;
    let root_terms = combination_terms(combination)?;
    require_term_count(root_terms, false)?;
    let nested = root_terms
        .iter()
        .any(|term| term.get("ref_kind").and_then(Value::as_str) == Some("load_combination"));
    if !nested {
        let referenced_ids = root_terms
            .iter()
            .map(|term| require_direct_term(term, patterns))
            .collect::<Result<Vec<_>, _>>()?;
        if referenced_ids
            .iter()
            .enumerate()
            .any(|(index, id)| referenced_ids[..index].iter().any(|prior| prior == id))
        {
            return Err(WorkbenchError::new(
                "workbench_model_linear_combination_request_duplicate_pattern",
                "selected direct load combination must reference unique load patterns",
            ));
        }
        return Ok(ExpandedLinearLoadCombinationV1 {
            root_terms: Value::Array(root_terms.clone()),
            expanded_pattern_terms: Value::Array(root_terms.clone()),
            max_depth: 1,
            expanded_term_count: root_terms.len(),
            nested: false,
        });
    }

    let mut expansion = ExpansionState::default();
    expand_combination(combination, combinations, patterns, 1.0, 1, &mut expansion)?;
    expansion.patterns.retain(|(_, factor)| *factor != 0.0);
    if !(MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
        ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1)
        .contains(&expansion.patterns.len())
    {
        return Err(WorkbenchError::new(
            "workbench_model_linear_nested_combination_resolved_pattern_count_unsupported",
            "selected nested load combination must resolve to between two and 64 nonzero unique patterns",
        ));
    }
    let expanded_pattern_terms = Value::Array(
        expansion
            .patterns
            .iter()
            .map(|(id, factor)| json!({"ref_id": id, "ref_kind": "load_pattern", "factor": factor}))
            .collect(),
    );
    Ok(ExpandedLinearLoadCombinationV1 {
        root_terms: Value::Array(root_terms.clone()),
        expanded_pattern_terms,
        max_depth: expansion.max_depth,
        expanded_term_count: expansion.expanded_term_count,
        nested: true,
    })
}

#[derive(Default)]
struct ExpansionState {
    active: Vec<String>,
    patterns: Vec<(String, f64)>,
    max_depth: usize,
    expanded_term_count: usize,
}

fn expand_combination(
    combination: &Value,
    combinations: &[Value],
    patterns: &[Value],
    parent_factor: f64,
    depth: usize,
    state: &mut ExpansionState,
) -> Result<(), WorkbenchError> {
    let id = combination
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| snapshot_error("selected load combination has no identity"))?;
    if depth > MODEL_LINEAR_LOAD_COMBINATION_MAX_NESTED_DEPTH_V1 {
        return Err(WorkbenchError::new(
            "workbench_model_linear_nested_combination_depth_unsupported",
            "selected nested load combination exceeds the maximum depth of eight",
        ));
    }
    if state.active.iter().any(|active| active == id) {
        return Err(WorkbenchError::new(
            "workbench_model_linear_nested_combination_cycle",
            "selected nested load combination contains a cycle",
        ));
    }
    require_linear_type(combination, id)?;
    let terms = combination_terms(combination)?;
    require_term_count(terms, true)?;
    state.max_depth = state.max_depth.max(depth);
    state.active.push(id.to_owned());
    for term in terms {
        let factor = require_factor(term, true)?;
        let scaled_factor = parent_factor * factor;
        if !scaled_factor.is_finite() || scaled_factor == 0.0 {
            return Err(WorkbenchError::new(
                "workbench_model_linear_nested_combination_factor_limit",
                "nested load-combination factor propagation exceeds the finite numerical domain",
            ));
        }
        let reference_id = term.get("ref_id").and_then(Value::as_str).ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_terms_invalid",
                "selected load-combination term has no reference identity",
            )
        })?;
        match term.get("ref_kind").and_then(Value::as_str) {
            Some("load_combination") => {
                let nested = find_combination(combinations, reference_id).ok_or_else(|| {
                    WorkbenchError::new(
                        "workbench_model_linear_nested_combination_reference_missing",
                        format!(
                            "ModelIR has no nested load combination with identity {reference_id}"
                        ),
                    )
                })?;
                expand_combination(
                    nested,
                    combinations,
                    patterns,
                    scaled_factor,
                    depth + 1,
                    state,
                )?;
            }
            Some("load_pattern") => {
                state.expanded_term_count += 1;
                if state.expanded_term_count > MODEL_LINEAR_LOAD_COMBINATION_MAX_EXPANDED_TERMS_V1 {
                    return Err(WorkbenchError::new(
                        "workbench_model_linear_nested_combination_expansion_unsupported",
                        "selected nested load combination expands beyond 64 pattern terms",
                    ));
                }
                require_linear_pattern(patterns, reference_id)?;
                if let Some((_, accumulated)) = state
                    .patterns
                    .iter_mut()
                    .find(|(prior, _)| prior == reference_id)
                {
                    let next = *accumulated + scaled_factor;
                    if !next.is_finite() {
                        return Err(WorkbenchError::new(
                            "workbench_model_linear_nested_combination_factor_limit",
                            "nested load-combination factor accumulation exceeds the finite numerical domain",
                        ));
                    }
                    *accumulated = if next == 0.0 { 0.0 } else { next };
                } else {
                    state
                        .patterns
                        .push((reference_id.to_owned(), scaled_factor));
                }
            }
            _ => {
                return Err(WorkbenchError::new(
                    "workbench_model_linear_combination_request_terms_invalid",
                    "selected load-combination term has an unsupported reference kind",
                ));
            }
        }
    }
    state.active.pop();
    Ok(())
}

fn find_combination<'a>(combinations: &'a [Value], id: &str) -> Option<&'a Value> {
    combinations
        .iter()
        .find(|combination| combination.get("id").and_then(Value::as_str) == Some(id))
}

fn combination_terms(combination: &Value) -> Result<&Vec<Value>, WorkbenchError> {
    combination
        .get("terms")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_terms_invalid",
                "selected load combination has no term array",
            )
        })
}

fn require_linear_type(combination: &Value, id: &str) -> Result<(), WorkbenchError> {
    if combination.get("combination_type").and_then(Value::as_str) != Some("linear") {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_type_unsupported",
            format!("load combination {id} is not linear"),
        ));
    }
    Ok(())
}

fn require_term_count(terms: &[Value], nested: bool) -> Result<(), WorkbenchError> {
    if !(MODEL_LINEAR_LOAD_COMBINATION_MIN_DIRECT_TERMS_V1
        ..=MODEL_LINEAR_LOAD_COMBINATION_MAX_DIRECT_TERMS_V1)
        .contains(&terms.len())
    {
        let detail = if nested {
            "each nested load combination must contain between two and 64 terms"
        } else {
            "selected direct load combination must contain between two and 64 terms"
        };
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_term_count_unsupported",
            detail,
        ));
    }
    Ok(())
}

fn require_direct_term<'a>(term: &'a Value, patterns: &[Value]) -> Result<&'a str, WorkbenchError> {
    if term.get("ref_kind").and_then(Value::as_str) != Some("load_pattern") {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_nested_unsupported",
            "selected load combination may reference load patterns only",
        ));
    }
    let reference_id = term.get("ref_id").and_then(Value::as_str).ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_linear_combination_request_terms_invalid",
            "selected load-combination term has no reference identity",
        )
    })?;
    require_factor(term, false)?;
    require_linear_pattern(patterns, reference_id)?;
    Ok(reference_id)
}

fn require_factor(term: &Value, nested: bool) -> Result<f64, WorkbenchError> {
    let factor = term.get("factor").and_then(Value::as_f64).ok_or_else(|| {
        WorkbenchError::new(
            "workbench_model_linear_combination_request_terms_invalid",
            "selected load-combination factor is not numeric",
        )
    })?;
    if !factor.is_finite() || factor == 0.0 {
        let detail = if nested {
            "nested load-combination factors must be finite and nonzero"
        } else {
            "selected load-combination factors must be finite and nonzero"
        };
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_factor_unsupported",
            detail,
        ));
    }
    Ok(factor)
}

fn require_linear_pattern(patterns: &[Value], id: &str) -> Result<(), WorkbenchError> {
    let pattern = patterns
        .iter()
        .find(|pattern| pattern.get("id").and_then(Value::as_str) == Some(id))
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_model_linear_combination_request_pattern_missing",
                format!("ModelIR has no load pattern with identity {id}"),
            )
        })?;
    if pattern.get("analysis_type").and_then(Value::as_str) != Some("linear_static") {
        return Err(WorkbenchError::new(
            "workbench_model_linear_combination_request_pattern_unsupported",
            format!("load pattern {id} is not linear_static"),
        ));
    }
    Ok(())
}

fn snapshot_error(detail: &str) -> WorkbenchError {
    WorkbenchError::new(
        "workbench_model_linear_combination_request_snapshot_invalid",
        detail,
    )
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Value};

    use super::require_bounded_linear_load_combination;

    fn pattern(id: &str) -> Value {
        json!({"id": id, "analysis_type": "linear_static"})
    }

    fn combination(id: &str, index: usize, terms: &Value) -> Value {
        json!({
            "id": id,
            "index": index,
            "combination_type": "linear",
            "terms": terms,
            "source_id": null,
            "extensions": {}
        })
    }

    #[test]
    fn nested_expansion_preserves_first_pattern_order_and_consolidates_factors() {
        let model = json!({
            "load_patterns": [pattern("P0"), pattern("P1"), pattern("P2")],
            "load_combinations": [
                combination("BASE", 0, &json!([
                    {"ref_id": "P0", "ref_kind": "load_pattern", "factor": 1.2},
                    {"ref_id": "P1", "ref_kind": "load_pattern", "factor": -0.5}
                ])),
                combination("NESTED", 1, &json!([
                    {"ref_id": "BASE", "ref_kind": "load_combination", "factor": 0.5},
                    {"ref_id": "P0", "ref_kind": "load_pattern", "factor": 0.4},
                    {"ref_id": "P2", "ref_kind": "load_pattern", "factor": 0.25}
                ]))
            ]
        });
        let expanded = require_bounded_linear_load_combination(&model, "NESTED")
            .expect("bounded nested expansion");
        assert!(expanded.nested);
        assert_eq!(expanded.max_depth, 2);
        assert_eq!(expanded.expanded_term_count, 4);
        assert_eq!(
            expanded.expanded_pattern_terms,
            json!([
                {"ref_id": "P0", "ref_kind": "load_pattern", "factor": 1.0},
                {"ref_id": "P1", "ref_kind": "load_pattern", "factor": -0.25},
                {"ref_id": "P2", "ref_kind": "load_pattern", "factor": 0.25}
            ])
        );
    }

    #[test]
    fn nested_expansion_rejects_depth_nine_and_65_leaf_contributions() {
        let mut deep_combinations = Vec::new();
        for index in 0..9 {
            let first = if index == 8 {
                json!({"ref_id": "P0", "ref_kind": "load_pattern", "factor": 1})
            } else {
                json!({
                    "ref_id": format!("D{}", index + 1),
                    "ref_kind": "load_combination",
                    "factor": 1
                })
            };
            deep_combinations.push(combination(
                &format!("D{index}"),
                index,
                &json!([
                    first,
                    {"ref_id": "P1", "ref_kind": "load_pattern", "factor": 1}
                ]),
            ));
        }
        let deep = json!({
            "load_patterns": [pattern("P0"), pattern("P1")],
            "load_combinations": deep_combinations
        });
        assert_eq!(
            require_bounded_linear_load_combination(&deep, "D0")
                .expect_err("depth nine")
                .code,
            "workbench_model_linear_nested_combination_depth_unsupported"
        );

        let repeated = (0..64)
            .map(|_| json!({"ref_id": "P0", "ref_kind": "load_pattern", "factor": 1}))
            .collect::<Vec<_>>();
        let expanded = json!({
            "load_patterns": [pattern("P0"), pattern("P1")],
            "load_combinations": [
                combination("LEAF", 0, &Value::Array(repeated)),
                combination("ROOT", 1, &json!([
                    {"ref_id": "LEAF", "ref_kind": "load_combination", "factor": 1},
                    {"ref_id": "P1", "ref_kind": "load_pattern", "factor": 1}
                ]))
            ]
        });
        assert_eq!(
            require_bounded_linear_load_combination(&expanded, "ROOT")
                .expect_err("65 expanded leaves")
                .code,
            "workbench_model_linear_nested_combination_expansion_unsupported"
        );
    }

    #[test]
    fn nested_expansion_rejects_cancellation_to_one_pattern() {
        let model = json!({
            "load_patterns": [pattern("P0"), pattern("P1")],
            "load_combinations": [
                combination("BASE", 0, &json!([
                    {"ref_id": "P0", "ref_kind": "load_pattern", "factor": 1},
                    {"ref_id": "P1", "ref_kind": "load_pattern", "factor": 1}
                ])),
                combination("ROOT", 1, &json!([
                    {"ref_id": "BASE", "ref_kind": "load_combination", "factor": 1},
                    {"ref_id": "P0", "ref_kind": "load_pattern", "factor": -1}
                ]))
            ]
        });
        assert_eq!(
            require_bounded_linear_load_combination(&model, "ROOT")
                .expect_err("one nonzero resolved pattern")
                .code,
            "workbench_model_linear_nested_combination_resolved_pattern_count_unsupported"
        );
    }
}
