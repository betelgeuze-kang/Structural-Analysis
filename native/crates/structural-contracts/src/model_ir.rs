//! Strict `ModelIR` v2 wire decoding and Python-compatible canonical identity.

use std::collections::BTreeSet;
use std::fmt::{self, Write as _};
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde::Serialize;
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};

use crate::MODEL_IR_SCHEMA_V2;

const MODEL_IR_SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/model_ir_v2.schema.json"
));
const DUPLICATE_KEY_SENTINEL: &str = "structural_duplicate_json_object_key";
const SEMANTIC_KEYS: [&str; 14] = [
    "schema_version",
    "capability_profile",
    "units",
    "coordinate_system",
    "dof_components",
    "nodes",
    "materials",
    "sections",
    "elements",
    "constraints",
    "load_patterns",
    "load_combinations",
    "time_functions",
    "construction_stages",
];
const SOURCE_FAMILIES: [&str; 9] = [
    "nodes",
    "materials",
    "sections",
    "elements",
    "constraints",
    "load_patterns",
    "load_combinations",
    "time_functions",
    "construction_stages",
];
const EXACT_INTEGER_FIELDS: [&str; 5] = [
    "index",
    "concrete_layer_count",
    "top_bar_count",
    "bottom_bar_count",
    "integration_order",
];

static SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

/// Stable validation issue serialized at the Rust wire boundary.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub struct ModelIrValidationIssue {
    pub code: String,
    pub path: String,
    pub detail: String,
}

/// Schema-only report for Slice B. Semantic validity remains a C++ Slice C concern.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ModelIrWireValidationReport {
    pub schema_version: &'static str,
    pub model_ir_schema_version: &'static str,
    pub schema_valid: bool,
    pub issues: Vec<ModelIrValidationIssue>,
    pub claim_boundary: &'static str,
}

/// Stable, log-safe failure returned before any C++ `ModelIR` call is possible.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ModelIrContractError {
    pub code: String,
    pub path: String,
    pub detail: String,
    pub issues: Vec<ModelIrValidationIssue>,
}

impl fmt::Display for ModelIrContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for ModelIrContractError {}

/// Validated immutable wire document and its three deterministic identities.
#[derive(Clone, Debug)]
pub struct ModelIrV2Document {
    value: Value,
    canonical_json: String,
    content_hash: String,
    semantic_hash: String,
    provenance_hash: String,
    model_id: String,
    capability_profile: String,
}

impl ModelIrV2Document {
    #[must_use]
    pub fn value(&self) -> &Value {
        &self.value
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn canonical_bytes(&self) -> &[u8] {
        self.canonical_json.as_bytes()
    }

    #[must_use]
    pub fn content_hash(&self) -> &str {
        &self.content_hash
    }

    #[must_use]
    pub fn semantic_hash(&self) -> &str {
        &self.semantic_hash
    }

    #[must_use]
    pub fn provenance_hash(&self) -> &str {
        &self.provenance_hash
    }

    #[must_use]
    pub fn model_id(&self) -> &str {
        &self.model_id
    }

    #[must_use]
    pub fn capability_profile(&self) -> &str {
        &self.capability_profile
    }
}

/// Decode UTF-8 JSON without accepting duplicate object keys or trailing data.
///
/// # Errors
///
/// Returns a stable contract error for invalid UTF-8, duplicate keys, invalid
/// JSON syntax, trailing data or an out-of-range wire number.
pub fn decode_json_strict(bytes: &[u8]) -> Result<Value, ModelIrContractError> {
    let text = std::str::from_utf8(bytes).map_err(|_| {
        contract_error(
            "model_ir_invalid_utf8",
            "/",
            "ModelIR input is not valid UTF-8",
        )
    })?;
    let mut deserializer = serde_json::Deserializer::from_str(text);
    let value = StrictValueSeed
        .deserialize(&mut deserializer)
        .map_err(|error| {
            let message = error.to_string();
            let code = if message.contains(DUPLICATE_KEY_SENTINEL) {
                "model_ir_duplicate_json_key"
            } else if message.contains("number out of range") {
                "model_ir_json_number_out_of_range"
            } else {
                "model_ir_invalid_json"
            };
            let detail = if code == "model_ir_duplicate_json_key" {
                "ModelIR JSON contains a duplicate object key".to_owned()
            } else if code == "model_ir_json_number_out_of_range" {
                "ModelIR JSON number exceeds the supported wire range".to_owned()
            } else {
                format!(
                    "ModelIR JSON syntax is invalid at line {} column {}",
                    error.line(),
                    error.column()
                )
            };
            contract_error(code, "/", &detail)
        })?;
    deserializer.end().map_err(|error| {
        contract_error(
            "model_ir_invalid_json",
            "/",
            &format!(
                "ModelIR JSON has trailing data at line {} column {}",
                error.line(),
                error.column()
            ),
        )
    })?;
    Ok(value)
}

/// Validate the current `ModelIR` v2 JSON Schema without claiming semantic readiness.
///
/// # Errors
///
/// Returns an error only when the embedded schema contract cannot be compiled.
/// Instance violations are returned as a deterministic invalid report.
pub fn validate_model_ir_v2_wire(
    value: &Value,
) -> Result<ModelIrWireValidationReport, ModelIrContractError> {
    let validator = schema_validator()?;
    let mut issues = validator
        .validate(value)
        .err()
        .into_iter()
        .flatten()
        .map(|error| {
            let instance_path = error.instance_path.to_string();
            let schema_path = error.schema_path.to_string();
            ModelIrValidationIssue {
                code: "schema_validation_error".to_owned(),
                path: if instance_path.is_empty() {
                    "/".to_owned()
                } else {
                    instance_path
                },
                detail: format!(
                    "value does not satisfy ModelIR v2 schema rule {}",
                    if schema_path.is_empty() {
                        "/"
                    } else {
                        &schema_path
                    }
                ),
            }
        })
        .collect::<Vec<_>>();
    collect_exact_integer_issues(value, "", &mut issues);
    issues.sort();
    issues.dedup();
    Ok(ModelIrWireValidationReport {
        schema_version: "structural-model-ir-wire-validation.v1",
        model_ir_schema_version: MODEL_IR_SCHEMA_V2,
        schema_valid: issues.is_empty(),
        issues,
        claim_boundary: "json_schema_and_canonical_identity_not_semantic_or_solver_readiness",
    })
}

/// Strictly decode, schema-validate and bind canonical `ModelIR` identities.
///
/// # Errors
///
/// Returns a stable contract error when decoding, schema validation,
/// canonicalization or required projection construction fails.
pub fn parse_model_ir_v2(bytes: &[u8]) -> Result<ModelIrV2Document, ModelIrContractError> {
    let value = decode_json_strict(bytes)?;
    let report = validate_model_ir_v2_wire(&value)?;
    if !report.schema_valid {
        return Err(ModelIrContractError {
            code: "model_ir_schema_invalid".to_owned(),
            path: "/".to_owned(),
            detail: "ModelIR input does not satisfy the v2 JSON Schema".to_owned(),
            issues: report.issues,
        });
    }

    let canonical_json = canonicalize_model_ir_v2(&value)?;
    let semantic = semantic_projection(&value)?;
    let provenance = provenance_projection(&value)?;
    let model_id = required_string(&value, "model_id")?.to_owned();
    let capability_profile = required_string(&value, "capability_profile")?.to_owned();
    Ok(ModelIrV2Document {
        content_hash: sha256_identity(canonical_json.as_bytes()),
        semantic_hash: hash_projection(&semantic)?,
        provenance_hash: hash_projection(&provenance)?,
        value,
        canonical_json,
        model_id,
        capability_profile,
    })
}

/// Render the exact compact, sorted and number-normalized Python compatibility bytes.
///
/// # Errors
///
/// Returns an error if a value cannot be represented by the bounded canonical
/// number or string contract.
pub fn canonicalize_model_ir_v2(value: &Value) -> Result<String, ModelIrContractError> {
    let mut output = String::new();
    write_canonical(value, &mut output)?;
    Ok(output)
}

/// Build the physical-meaning projection, excluding source and extension metadata.
///
/// # Errors
///
/// Returns an invariant error when called on a value that has not passed the
/// required `ModelIR` v2 schema.
pub fn semantic_projection(value: &Value) -> Result<Value, ModelIrContractError> {
    let object = required_object(value, "/")?;
    let mut projection = Map::new();
    for key in SEMANTIC_KEYS {
        let item = object.get(key).ok_or_else(|| invariant_error(key))?;
        projection.insert(key.to_owned(), without_source_metadata(item));
    }
    Ok(Value::Object(projection))
}

/// Build the source-identity projection without normalized physical values.
///
/// # Errors
///
/// Returns an invariant error when called on a value that has not passed the
/// required `ModelIR` v2 schema.
pub fn provenance_projection(value: &Value) -> Result<Value, ModelIrContractError> {
    let object = required_object(value, "/")?;
    let mut projection = Map::new();
    for key in [
        "schema_version",
        "capability_profile",
        "model_id",
        "provenance",
    ] {
        projection.insert(
            key.to_owned(),
            object.get(key).ok_or_else(|| invariant_error(key))?.clone(),
        );
    }

    let mut family_metadata = Map::new();
    for family in SOURCE_FAMILIES {
        let rows = object
            .get(family)
            .and_then(Value::as_array)
            .ok_or_else(|| invariant_error(family))?;
        let metadata = rows
            .iter()
            .map(source_metadata)
            .collect::<Result<Vec<_>, _>>()?;
        family_metadata.insert(family.to_owned(), Value::Array(metadata));
    }
    projection.insert(
        "entity_source_metadata".to_owned(),
        Value::Object(family_metadata),
    );
    for key in ["roundtrip_map", "unsupported_features", "extensions"] {
        projection.insert(
            key.to_owned(),
            object.get(key).ok_or_else(|| invariant_error(key))?.clone(),
        );
    }
    Ok(Value::Object(projection))
}

fn schema_validator() -> Result<&'static JSONSchema, ModelIrContractError> {
    let compiled = SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(MODEL_IR_SCHEMA_TEXT)
            .map_err(|error| format!("schema JSON invalid: {error}"))?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|error| format!("schema compile failed: {error}"))
    });
    compiled.as_ref().map_err(|_| {
        contract_error(
            "model_ir_schema_contract_invalid",
            "/",
            "embedded ModelIR v2 schema could not be compiled",
        )
    })
}

fn hash_projection(value: &Value) -> Result<String, ModelIrContractError> {
    Ok(sha256_identity(canonicalize_model_ir_v2(value)?.as_bytes()))
}

fn sha256_identity(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{digest:x}")
}

fn write_canonical(value: &Value, output: &mut String) -> Result<(), ModelIrContractError> {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(flag) => output.push_str(if *flag { "true" } else { "false" }),
        Value::Number(number) => output.push_str(&canonical_number(number)?),
        Value::String(text) => {
            let escaped = serde_json::to_string(text).map_err(|_| {
                contract_error(
                    "model_ir_canonicalization_failed",
                    "/",
                    "ModelIR string could not be encoded",
                )
            })?;
            output.push_str(&escaped);
        }
        Value::Array(items) => {
            output.push('[');
            for (index, item) in items.iter().enumerate() {
                if index != 0 {
                    output.push(',');
                }
                write_canonical(item, output)?;
            }
            output.push(']');
        }
        Value::Object(object) => {
            output.push('{');
            let mut keys = object.keys().collect::<Vec<_>>();
            keys.sort_unstable();
            for (index, key) in keys.into_iter().enumerate() {
                if index != 0 {
                    output.push(',');
                }
                let escaped = serde_json::to_string(key).map_err(|_| {
                    contract_error(
                        "model_ir_canonicalization_failed",
                        "/",
                        "ModelIR object key could not be encoded",
                    )
                })?;
                output.push_str(&escaped);
                output.push(':');
                write_canonical(&object[key], output)?;
            }
            output.push('}');
        }
    }
    Ok(())
}

fn canonical_number(number: &Number) -> Result<String, ModelIrContractError> {
    if let Some(value) = number.as_i64() {
        return Ok(value.to_string());
    }
    if let Some(value) = number.as_u64() {
        return Ok(value.to_string());
    }
    let value = number.as_f64().ok_or_else(|| {
        contract_error(
            "model_ir_json_number_out_of_range",
            "/",
            "ModelIR JSON number exceeds the supported wire range",
        )
    })?;
    if !value.is_finite() {
        return Err(contract_error(
            "model_ir_non_finite_number",
            "/",
            "ModelIR contains a non-finite number",
        ));
    }
    if value == 0.0 {
        return Ok("0".to_owned());
    }
    if value.fract() == 0.0 {
        return Ok(format!("{value:.0}"));
    }
    Ok(python_compatible_float(value))
}

fn python_compatible_float(value: f64) -> String {
    let shortest = Number::from_f64(value)
        .expect("finite value has a JSON number representation")
        .to_string();
    let (sign, unsigned) = shortest
        .strip_prefix('-')
        .map_or(("", shortest.as_str()), |rest| ("-", rest));
    let (mantissa, explicit_exponent) =
        unsigned
            .split_once(['e', 'E'])
            .map_or((unsigned, 0), |(left, right)| {
                (
                    left,
                    right
                        .parse::<i32>()
                        .expect("serde_json emits a bounded decimal exponent"),
                )
            });
    let decimal_position = mantissa.find('.').unwrap_or(mantissa.len());
    let digits = mantissa.replace('.', "");
    let first_nonzero = digits
        .bytes()
        .position(|byte| byte != b'0')
        .expect("nonzero float has a nonzero decimal digit");
    let significant = &digits[first_nonzero..];
    let scientific_exponent = explicit_exponent
        + i32::try_from(decimal_position).expect("float rendering length is bounded")
        - i32::try_from(first_nonzero).expect("float rendering length is bounded")
        - 1;

    let mut output = String::from(sign);
    if !(-4..16).contains(&scientific_exponent) {
        output.push(significant.as_bytes()[0] as char);
        if significant.len() > 1 {
            output.push('.');
            output.push_str(&significant[1..]);
        }
        output.push('e');
        output.push(if scientific_exponent < 0 { '-' } else { '+' });
        let magnitude = scientific_exponent.unsigned_abs();
        write!(output, "{magnitude:02}").expect("writing to an owned String cannot fail");
        return output;
    }

    let fixed_position = scientific_exponent + 1;
    if fixed_position <= 0 {
        output.push_str("0.");
        for _ in 0..fixed_position.unsigned_abs() {
            output.push('0');
        }
        output.push_str(significant);
    } else {
        let fixed_position = usize::try_from(fixed_position)
            .expect("nonnegative decimal position converts to usize");
        if fixed_position >= significant.len() {
            output.push_str(significant);
            for _ in significant.len()..fixed_position {
                output.push('0');
            }
        } else {
            output.push_str(&significant[..fixed_position]);
            output.push('.');
            output.push_str(&significant[fixed_position..]);
        }
    }
    output
}

fn without_source_metadata(value: &Value) -> Value {
    match value {
        Value::Object(object) => Value::Object(
            object
                .iter()
                .filter(|(key, _)| key.as_str() != "source_id" && key.as_str() != "extensions")
                .map(|(key, item)| (key.clone(), without_source_metadata(item)))
                .collect(),
        ),
        Value::Array(items) => Value::Array(items.iter().map(without_source_metadata).collect()),
        _ => value.clone(),
    }
}

fn source_metadata(value: &Value) -> Result<Value, ModelIrContractError> {
    let row = required_object(value, "/")?;
    let mut metadata = Map::new();
    for key in ["id", "index", "extensions"] {
        metadata.insert(
            key.to_owned(),
            row.get(key).ok_or_else(|| invariant_error(key))?.clone(),
        );
    }
    if let Some(source_id) = row.get("source_id") {
        metadata.insert("source_id".to_owned(), source_id.clone());
    }
    if let Some(nodal_loads) = row.get("nodal_loads") {
        let loads = nodal_loads
            .as_array()
            .ok_or_else(|| invariant_error("nodal_loads"))?
            .iter()
            .map(source_metadata)
            .collect::<Result<Vec<_>, _>>()?;
        metadata.insert("nodal_loads".to_owned(), Value::Array(loads));
    }
    if let Some(member_loads) = row.get("uniform_member_loads") {
        let loads = member_loads
            .as_array()
            .ok_or_else(|| invariant_error("uniform_member_loads"))?
            .iter()
            .map(source_metadata)
            .collect::<Result<Vec<_>, _>>()?;
        metadata.insert("uniform_member_loads".to_owned(), Value::Array(loads));
    }
    Ok(Value::Object(metadata))
}

fn collect_exact_integer_issues(
    value: &Value,
    path: &str,
    issues: &mut Vec<ModelIrValidationIssue>,
) {
    match value {
        Value::Object(object) => {
            for (key, item) in object {
                if key == "extensions" {
                    continue;
                }
                let child_path = format!("{}/{}", path, escape_json_pointer(key));
                if EXACT_INTEGER_FIELDS.contains(&key.as_str())
                    && item.as_number().is_some_and(Number::is_f64)
                {
                    issues.push(ModelIrValidationIssue {
                        code: "schema_validation_error".to_owned(),
                        path: child_path.clone(),
                        detail: "value must use the exact JSON integer type".to_owned(),
                    });
                }
                collect_exact_integer_issues(item, &child_path, issues);
            }
        }
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                collect_exact_integer_issues(item, &format!("{path}/{index}"), issues);
            }
        }
        _ => {}
    }
}

fn escape_json_pointer(value: &str) -> String {
    value.replace('~', "~0").replace('/', "~1")
}

fn required_object<'a>(
    value: &'a Value,
    path: &str,
) -> Result<&'a Map<String, Value>, ModelIrContractError> {
    value.as_object().ok_or_else(|| {
        contract_error(
            "model_ir_contract_invariant",
            path,
            "validated ModelIR value is not an object",
        )
    })
}

fn required_string<'a>(value: &'a Value, key: &str) -> Result<&'a str, ModelIrContractError> {
    required_object(value, "/")?
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| invariant_error(key))
}

fn invariant_error(field: &str) -> ModelIrContractError {
    contract_error(
        "model_ir_contract_invariant",
        &format!("/{}", escape_json_pointer(field)),
        "validated ModelIR value is missing a required typed field",
    )
}

fn contract_error(code: &str, path: &str, detail: &str) -> ModelIrContractError {
    ModelIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
        issues: Vec::new(),
    }
}

struct StrictValueSeed;

impl<'de> DeserializeSeed<'de> for StrictValueSeed {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictValueVisitor)
    }
}

struct StrictValueVisitor;

impl<'de> Visitor<'de> for StrictValueVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_i128<E>(self, value: i128) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Number::from_i128(value)
            .map(Value::Number)
            .ok_or_else(|| E::custom("number out of range"))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_u128<E>(self, value: u128) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Number::from_u128(value)
            .map(Value::Number)
            .ok_or_else(|| E::custom("number out of range"))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(Value::String(value))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::with_capacity(sequence.size_hint().unwrap_or(0));
        while let Some(value) = sequence.next_element_seed(StrictValueSeed)? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }

    fn visit_map<A>(self, mut object: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        let mut keys = BTreeSet::new();
        while let Some(key) = object.next_key::<String>()? {
            if !keys.insert(key.clone()) {
                return Err(de::Error::custom(DUPLICATE_KEY_SENTINEL));
            }
            let value = object.next_value_seed(StrictValueSeed)?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{canonicalize_model_ir_v2, decode_json_strict, python_compatible_float};

    #[test]
    fn strict_decoder_rejects_duplicate_keys_at_any_depth() {
        let error = decode_json_strict(br#"{"outer":{"id":1,"id":2}}"#)
            .expect_err("duplicate key must fail before schema validation");
        assert_eq!(error.code, "model_ir_duplicate_json_key");
        assert!(error.issues.is_empty());
    }

    #[test]
    fn canonical_numbers_match_the_python_compatibility_contract() {
        let value = json!({
            "signed_zero": -0.0,
            "integral_float": 1.0,
            "small_1e5": 1e-5,
            "small_1e4": 1e-4,
            "small_1e6": 1e-6,
            "fraction": 1.234_567_890_123_456_7,
            "unicode": "구조/α",
            "huge_integral_float": 1e20,
        });
        assert_eq!(
            canonicalize_model_ir_v2(&value).expect("canonical JSON"),
            r#"{"fraction":1.2345678901234567,"huge_integral_float":100000000000000000000,"integral_float":1,"signed_zero":0,"small_1e4":0.0001,"small_1e5":1e-05,"small_1e6":1e-06,"unicode":"구조/α"}"#
        );
    }

    #[test]
    fn python_float_thresholds_are_explicit() {
        assert_eq!(python_compatible_float(0.0001), "0.0001");
        assert_eq!(python_compatible_float(0.00001), "1e-05");
        assert_eq!(python_compatible_float(-0.000_001_25), "-1.25e-06");
        assert_eq!(python_compatible_float(123.25), "123.25");
    }
}
