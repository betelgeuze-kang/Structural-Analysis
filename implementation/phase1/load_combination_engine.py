#!/usr/bin/env python3
"""Deterministic load-combination library for code-check workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_MIDAS_CASE_ALIAS = {
    "DEAD": "D",
    "LIVE": "L",
    "ROOF_LIVE": "Lr",
    "SNOW": "S",
    "WIND+X": "Wx",
    "WIND-X": "Wx",
    "WIND+Y": "Wy",
    "WIND-Y": "Wy",
    "WX": "Wx",
    "WY": "Wy",
    "SEISMIC_X": "Ex",
    "SEISMIC_Y": "Ey",
    "EX": "Ex",
    "EY": "Ey",
}

KDS_CONCRETE_FAMILY = "KDS-2022"
KDS_RC_BASIC_FAMILY = "KDS-2022-RC-BASIC"
KDS_RC_WIND_FAMILY = "KDS-2022-RC-WIND"
KDS_RC_SEISMIC_FAMILY = "KDS-2022-RC-SEISMIC"
KDS_RC_NESTED_FAMILY = "KDS-2022-RC-NESTED"
KDS_STEEL_BASIC_FAMILY = "KDS-2022-STEEL-BASIC"
KDS_GENERIC_GATE_FAMILY = "KDS-2022-generic"
KDS_RC_WIND_GATE_FAMILY = "KDS-2022-rc-wind"
KDS_RC_SEISMIC_GATE_FAMILY = "KDS-2022-rc-seismic"
KDS_RC_NESTED_GATE_FAMILY = "KDS-2022-rc-nested"
KDS_STEEL_GRAVITY_GATE_FAMILY = "KDS-2022-steel-gravity"

_FAMILY_ALIAS_MAP = {
    KDS_CONCRETE_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_BASIC_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_WIND_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_SEISMIC_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_NESTED_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_GENERIC_GATE_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_WIND_GATE_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_SEISMIC_GATE_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_RC_NESTED_GATE_FAMILY.upper(): KDS_CONCRETE_FAMILY,
    KDS_STEEL_BASIC_FAMILY.upper(): KDS_STEEL_BASIC_FAMILY,
    KDS_STEEL_GRAVITY_GATE_FAMILY.upper(): KDS_STEEL_BASIC_FAMILY,
}

_RC_CASE_KEYS = frozenset({"D", "L", "Lr", "S"})
_WIND_CASE_KEYS = frozenset({"Wx", "Wy"})
_SEISMIC_CASE_KEYS = frozenset({"Ex", "Ey"})
_CASE_FAMILY_ORDER = ("rc", "wind", "seismic")


@dataclass(frozen=True)
class LoadCombination:
    name: str
    family: str
    limit_state: str
    factors: dict[str, float]

    @property
    def envelope_scale(self) -> float:
        mags = [abs(float(v)) for v in self.factors.values()]
        if not mags:
            return 1.0
        mean_mag = float(sum(mags) / len(mags))
        return float(0.30 * max(mags) + 0.70 * mean_mag)


def generate_kds_strength_combinations() -> list[LoadCombination]:
    return [
        LoadCombination("KDS_ULS_1", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.4}),
        LoadCombination("KDS_ULS_2", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 1.6}),
        LoadCombination("KDS_ULS_3_WX+", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Wx": 1.0}),
        LoadCombination("KDS_ULS_3_WX-", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Wx": -1.0}),
        LoadCombination("KDS_ULS_4_WY+", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Wy": 1.0}),
        LoadCombination("KDS_ULS_4_WY-", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Wy": -1.0}),
        LoadCombination("KDS_ULS_5_EX+", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Ex": 1.0}),
        LoadCombination("KDS_ULS_5_EX-", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Ex": -1.0}),
        LoadCombination("KDS_ULS_6_EY+", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Ey": 1.0}),
        LoadCombination("KDS_ULS_6_EY-", KDS_CONCRETE_FAMILY, "ULS", {"D": 1.2, "L": 0.5, "Ey": -1.0}),
        LoadCombination("KDS_ULS_7_RSX+", KDS_CONCRETE_FAMILY, "ULS", {"D": 0.9, "Ex": 1.0}),
        LoadCombination("KDS_ULS_7_RSX-", KDS_CONCRETE_FAMILY, "ULS", {"D": 0.9, "Ex": -1.0}),
        LoadCombination("KDS_ULS_8_RSY+", KDS_CONCRETE_FAMILY, "ULS", {"D": 0.9, "Ey": 1.0}),
        LoadCombination("KDS_ULS_8_RSY-", KDS_CONCRETE_FAMILY, "ULS", {"D": 0.9, "Ey": -1.0}),
    ]


def generate_kds_service_combinations() -> list[LoadCombination]:
    return [
        LoadCombination("KDS_SLS_1", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 1.0}),
        LoadCombination("KDS_SLS_2_WX+", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Wx": 0.7}),
        LoadCombination("KDS_SLS_2_WX-", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Wx": -0.7}),
        LoadCombination("KDS_SLS_3_WY+", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Wy": 0.7}),
        LoadCombination("KDS_SLS_3_WY-", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Wy": -0.7}),
        LoadCombination("KDS_SLS_4_EX+", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Ex": 0.7}),
        LoadCombination("KDS_SLS_4_EX-", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Ex": -0.7}),
        LoadCombination("KDS_SLS_5_EY+", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Ey": 0.7}),
        LoadCombination("KDS_SLS_5_EY-", KDS_CONCRETE_FAMILY, "SLS", {"D": 1.0, "L": 0.5, "Ey": -0.7}),
    ]


def generate_kds_steel_strength_combinations() -> list[LoadCombination]:
    return [
        LoadCombination("KDS_STEEL_ULS_1", KDS_STEEL_BASIC_FAMILY, "ULS", {"D": 1.3, "L": 1.5}),
        LoadCombination("KDS_STEEL_ULS_2", KDS_STEEL_BASIC_FAMILY, "ULS", {"D": 1.0, "L": 1.5}),
    ]


def generate_kds_steel_service_combinations() -> list[LoadCombination]:
    return [
        LoadCombination("KDS_STEEL_SLS_1", KDS_STEEL_BASIC_FAMILY, "SLS", {"D": 1.0, "L": 1.0}),
    ]


def canonicalize_kds_family(family: str | None) -> str:
    normalized = str(family or "").strip()
    if not normalized:
        return KDS_CONCRETE_FAMILY
    return _FAMILY_ALIAS_MAP.get(normalized.upper(), normalized)


def _family_combinations(*, family: str, limit_state: str) -> list[LoadCombination]:
    family_normalized = canonicalize_kds_family(family).upper()
    state_normalized = str(limit_state).strip().upper()
    if family_normalized == KDS_CONCRETE_FAMILY.upper():
        return generate_kds_strength_combinations() if state_normalized == "ULS" else generate_kds_service_combinations()
    if family_normalized == KDS_STEEL_BASIC_FAMILY.upper():
        return (
            generate_kds_steel_strength_combinations()
            if state_normalized == "ULS"
            else generate_kds_steel_service_combinations()
        )
    raise ValueError(f"unsupported family: {family}")


def generate_named_scale_library(
    *,
    family: str = KDS_CONCRETE_FAMILY,
    limit_state: str = "ULS",
) -> list[tuple[str, float]]:
    combos = _family_combinations(family=family, limit_state=limit_state)
    return [(combo.name, combo.envelope_scale) for combo in combos]


def normalize_runtime_case_name(case_name: str) -> str:
    text = str(case_name).strip().upper()
    return _MIDAS_CASE_ALIAS.get(text, text)


def _normalized_limit_state_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"ULS", "STRENGTH"}:
        return "ULS"
    if text in {"SLS", "SERVICE"}:
        return "SLS"
    return text or "UNSPECIFIED"


def _combo_case_family_profile(
    *,
    case_names: list[str],
    nested_reference_count: int,
    nested_depth: int,
) -> dict[str, Any]:
    normalized_cases = [normalize_runtime_case_name(case_name) for case_name in case_names if str(case_name).strip()]
    case_set = {case_name for case_name in normalized_cases if case_name}
    rc_present = bool(case_set & _RC_CASE_KEYS)
    wind_present = bool(case_set & _WIND_CASE_KEYS)
    seismic_present = bool(case_set & _SEISMIC_CASE_KEYS)
    nested_present = int(nested_reference_count) > 0 or int(nested_depth) > 1
    family_tags = [
        tag
        for tag, present in (
            ("rc", rc_present),
            ("wind", wind_present),
            ("seismic", seismic_present),
            ("nested", nested_present),
        )
        if present
    ]
    if not family_tags:
        family_tags = ["other"]
    return {
        "case_names": list(sorted(case_set)),
        "case_count": int(len(case_set)),
        "family_tags": family_tags,
        "family_label": "+".join(family_tags),
        "rc_present": bool(rc_present),
        "wind_present": bool(wind_present),
        "seismic_present": bool(seismic_present),
        "nested_present": bool(nested_present),
    }


def _normalized_factor_map(payload: Any) -> dict[str, float]:
    factor_map = payload if isinstance(payload, dict) else {}
    return {
        normalize_runtime_case_name(str(k)): float(v)
        for k, v in factor_map.items()
        if str(k).strip()
    }


def _clean_factor_map(factor_map: dict[str, float]) -> dict[str, float]:
    return {
        str(key): float(value)
        for key, value in sorted(factor_map.items())
        if abs(float(value)) > 1.0e-12
    }


def _load_combination_rows(model_payload: dict) -> list[dict[str, Any]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    combos = loads.get("load_combinations") if isinstance(loads.get("load_combinations"), list) else []
    return [row for row in combos if isinstance(row, dict)]


def _combo_lookup_keys(name: str) -> list[str]:
    normalized = str(name or "").strip()
    if not normalized:
        return []
    keys = [normalized]
    upper = normalized.upper()
    if upper != normalized:
        keys.append(upper)
    return keys


def _build_combo_row_lookup(combo_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in combo_rows:
        for key in _combo_lookup_keys(str(row.get("name", "") or "")):
            lookup.setdefault(key, row)
    return lookup


def _lookup_combo_row(
    combo_lookup: dict[str, dict[str, Any]],
    combo_name: str,
) -> dict[str, Any] | None:
    for key in _combo_lookup_keys(combo_name):
        matched = combo_lookup.get(key)
        if matched is not None:
            return matched
    return None


def _accumulate_factors(
    target: dict[str, float],
    source: dict[str, float],
    *,
    scale: float = 1.0,
) -> None:
    for key, value in source.items():
        target[str(key)] = float(target.get(str(key), 0.0)) + float(value) * float(scale)


def _derive_combo_factor_map_from_entry_rows(
    combo_row: dict[str, Any],
    *,
    combo_lookup: dict[str, dict[str, Any]],
    memo: dict[str, dict[str, float]],
    resolving: set[str],
) -> dict[str, float]:
    entry_rows = _editor_seed_entry_rows(combo_row)
    if not entry_rows:
        entry_rows = [
            {
                "reference_kind": "CB",
                "reference_name": str(reference_name).strip(),
                "factor": 1.0,
            }
            for reference_name in (combo_row.get("referenced_combinations") or [])
            if str(reference_name).strip()
        ]
    if not entry_rows:
        return {}

    derived: dict[str, float] = {}
    for row in entry_rows:
        reference_kind = str(row.get("reference_kind", "")).strip().upper()
        reference_name = str(row.get("reference_name", "")).strip()
        factor = float(row.get("factor", 0.0) or 0.0)
        if not reference_name or abs(factor) <= 1.0e-12:
            continue
        if reference_kind == "ST":
            case_name = normalize_runtime_case_name(reference_name)
            if case_name:
                derived[case_name] = float(derived.get(case_name, 0.0)) + factor
            continue
        if reference_kind != "CB":
            continue
        nested_row = _lookup_combo_row(combo_lookup, reference_name)
        if nested_row is None:
            continue
        nested_factors = _resolve_combo_factor_map(
            nested_row,
            combo_lookup=combo_lookup,
            memo=memo,
            resolving=resolving,
        )
        if nested_factors:
            _accumulate_factors(derived, nested_factors, scale=factor)
    return _clean_factor_map(derived)


def _resolve_combo_factor_map(
    combo_row: dict[str, Any],
    *,
    combo_lookup: dict[str, dict[str, Any]],
    memo: dict[str, dict[str, float]],
    resolving: set[str],
) -> dict[str, float]:
    combo_name = str(combo_row.get("name", "") or "").strip()
    memo_key = combo_name or f"__anonymous__:{id(combo_row)}"
    if memo_key in memo:
        return dict(memo[memo_key])
    if memo_key in resolving:
        return {}

    resolving.add(memo_key)
    try:
        expanded = _clean_factor_map(_normalized_factor_map(combo_row.get("expanded_factor_map") or {}))
        if expanded:
            memo[memo_key] = expanded
            return dict(expanded)

        derived = _derive_combo_factor_map_from_entry_rows(
            combo_row,
            combo_lookup=combo_lookup,
            memo=memo,
            resolving=resolving,
        )
        if derived:
            memo[memo_key] = derived
            return dict(derived)

        fallback = _clean_factor_map(_normalized_factor_map(combo_row.get("factor_map") or {}))
        memo[memo_key] = fallback
        return dict(fallback)
    finally:
        resolving.discard(memo_key)


def load_combinations_from_midas_model(model_payload: dict) -> list[LoadCombination]:
    combos = _load_combination_rows(model_payload)
    combo_lookup = _build_combo_row_lookup(combos)
    memo: dict[str, dict[str, float]] = {}
    out: list[LoadCombination] = []
    for row in combos:
        normalized = _resolve_combo_factor_map(
            row,
            combo_lookup=combo_lookup,
            memo=memo,
            resolving=set(),
        )
        out.append(
            LoadCombination(
                name=str(row.get("name", "")).strip(),
                family="MIDAS_TYPED",
                limit_state=str(row.get("limit_state", "")).strip() or str(row.get("combination_type", "")).strip(),
                factors=normalized,
            )
        )
    return out


def infer_combination_family_from_midas_model(model_payload: dict) -> str:
    combo_rows = _load_combination_rows(model_payload)
    if not combo_rows:
        return KDS_CONCRETE_FAMILY

    canonical_steel_maps = {
        tuple(sorted(combo.factors.items()))
        for combo in [*generate_kds_steel_strength_combinations(), *generate_kds_steel_service_combinations()]
    }
    combo_lookup = _build_combo_row_lookup(combo_rows)
    memo: dict[str, dict[str, float]] = {}
    observed_steel_maps: set[tuple[tuple[str, float], ...]] = set()
    for row in combo_rows:
        combination_type = str(row.get("combination_type", "") or "").strip().upper()
        combo_name = str(row.get("name", "") or "").strip().upper()
        if combination_type != "STEEL" and not combo_name.startswith("SLCB"):
            continue
        normalized = _resolve_combo_factor_map(
            row,
            combo_lookup=combo_lookup,
            memo=memo,
            resolving=set(),
        )
        if normalized:
            observed_steel_maps.add(tuple(sorted(normalized.items())))

    if canonical_steel_maps.issubset(observed_steel_maps):
        return KDS_STEEL_BASIC_FAMILY
    return KDS_CONCRETE_FAMILY


def match_runtime_to_kds(
    *,
    runtime_combinations: list[LoadCombination],
    kds_combinations: list[LoadCombination],
) -> list[dict]:
    out: list[dict] = []
    for kds in kds_combinations:
        best_name = ""
        best_score = -1.0
        best_factor_map: dict[str, float] = {}
        for runtime in runtime_combinations:
            keys = sorted(set(kds.factors.keys()) | set(runtime.factors.keys()))
            if not keys:
                score = 1.0
            else:
                diff = sum(abs(float(kds.factors.get(k, 0.0)) - float(runtime.factors.get(k, 0.0))) for k in keys)
                score = 1.0 / (1.0 + diff)
            if score > best_score:
                best_score = float(score)
                best_name = str(runtime.name)
                best_factor_map = {str(k): float(v) for k, v in sorted(runtime.factors.items())}
        out.append(
            {
                "kds_name": str(kds.name),
                "kds_factor_map": {str(k): float(v) for k, v in sorted(kds.factors.items())},
                "matched_runtime_name": best_name,
                "matched_runtime_factor_map": best_factor_map,
                "match_score": float(max(best_score, 0.0)),
            }
        )
    return out


def _editor_seed_runtime_combinations(editor_seed: dict[str, Any]) -> list[LoadCombination]:
    combination_rows = [
        {
            "name": str(row.get("name", "") or ""),
            "combination_type": str(row.get("combination_type", "") or "GEN"),
            "limit_state": str(row.get("limit_state", "") or ""),
            "entry_rows": [
                {
                    "reference_kind": str(entry.get("reference_kind", "") or "ST"),
                    "reference_name": str(entry.get("reference_name", "") or ""),
                    "factor": float(entry.get("factor", 0.0) or 0.0),
                }
                for entry in (row.get("entry_rows") or [])
                if isinstance(entry, dict)
            ],
            "factor_map": {
                str(key): float(value)
                for key, value in (row.get("factor_map") or {}).items()
            },
            "expanded_factor_map": {
                str(key): float(value)
                for key, value in (row.get("expanded_factor_map") or {}).items()
            },
            "referenced_combinations": [
                str(item)
                for item in (row.get("referenced_combinations") or [])
                if str(item).strip()
            ],
        }
        for row in (editor_seed.get("combination_nodes") or [])
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]
    return load_combinations_from_midas_model(
        {
            "model": {
                "loads": {
                    "load_combinations": combination_rows,
                }
            }
        }
    )


def _editor_seed_case_names(editor_seed: dict[str, Any]) -> list[str]:
    case_rows = [
        row
        for row in (editor_seed.get("case_nodes") or [])
        if isinstance(row, dict) and str(row.get("name", "") or "").strip()
    ]
    return [
        normalize_runtime_case_name(str(row.get("name", "") or ""))
        for row in case_rows
        if normalize_runtime_case_name(str(row.get("name", "") or ""))
    ]


def _required_editor_target_groups(
    *,
    family: str = KDS_CONCRETE_FAMILY,
) -> list[dict[str, Any]]:
    normalized_family = canonicalize_kds_family(family)
    if normalized_family == KDS_STEEL_BASIC_FAMILY:
        return [
            {
                "target_id": "steel_strength",
                "label": "Steel strength",
                "limit_state": "ULS",
                "threshold": 0.90,
                "kds_combinations": generate_kds_steel_strength_combinations(),
            },
            {
                "target_id": "steel_service",
                "label": "Steel service",
                "limit_state": "SLS",
                "threshold": 0.90,
                "kds_combinations": generate_kds_steel_service_combinations(),
            },
        ]

    strength_lookup = {combo.name: combo for combo in generate_kds_strength_combinations()}
    return [
        {
            "target_id": "gravity_dead",
            "label": "Gravity dead",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [strength_lookup["KDS_ULS_1"]],
        },
        {
            "target_id": "gravity_dead_live",
            "label": "Gravity dead + live",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [strength_lookup["KDS_ULS_2"]],
        },
        {
            "target_id": "wind_x",
            "label": "Wind X",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_3_WX+"],
                strength_lookup["KDS_ULS_3_WX-"],
            ],
        },
        {
            "target_id": "wind_y",
            "label": "Wind Y",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_4_WY+"],
                strength_lookup["KDS_ULS_4_WY-"],
            ],
        },
        {
            "target_id": "seismic_x",
            "label": "Seismic X",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_5_EX+"],
                strength_lookup["KDS_ULS_5_EX-"],
            ],
        },
        {
            "target_id": "seismic_y",
            "label": "Seismic Y",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_6_EY+"],
                strength_lookup["KDS_ULS_6_EY-"],
            ],
        },
        {
            "target_id": "stability_x",
            "label": "Stability X",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_7_RSX+"],
                strength_lookup["KDS_ULS_7_RSX-"],
            ],
        },
        {
            "target_id": "stability_y",
            "label": "Stability Y",
            "limit_state": "ULS",
            "threshold": 0.90,
            "kds_combinations": [
                strength_lookup["KDS_ULS_8_RSY+"],
                strength_lookup["KDS_ULS_8_RSY-"],
            ],
        },
    ]


def match_runtime_to_required_editor_targets(
    *,
    runtime_combinations: list[LoadCombination],
    family: str = KDS_CONCRETE_FAMILY,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for group in _required_editor_target_groups(family=family):
        best_row: dict[str, Any] = {}
        best_score = -1.0
        for row in match_runtime_to_kds(
            runtime_combinations=runtime_combinations,
            kds_combinations=list(group["kds_combinations"]),
        ):
            score = float(row.get("match_score", 0.0) or 0.0)
            if score > best_score:
                best_row = row
                best_score = score
        ready = best_score >= float(group.get("threshold", 0.90) or 0.90)
        rows.append(
            {
                "target_id": str(group.get("target_id", "") or ""),
                "label": str(group.get("label", "") or ""),
                "limit_state": str(group.get("limit_state", "") or ""),
                "threshold": float(group.get("threshold", 0.90) or 0.90),
                "ready": bool(ready),
                "match_score": float(max(best_score, 0.0)),
                "matched_runtime_name": str(best_row.get("matched_runtime_name", "") or ""),
                "matched_runtime_factor_map": dict(best_row.get("matched_runtime_factor_map", {}) or {}),
                "matched_kds_name": str(best_row.get("kds_name", "") or ""),
            }
        )
    ready_count = sum(1 for row in rows if bool(row.get("ready", False)))
    total_count = len(rows)
    return {
        "family": canonicalize_kds_family(family),
        "target_count": int(total_count),
        "ready_count": int(ready_count),
        "rows": rows,
        "contract_pass": bool(total_count > 0 and ready_count >= total_count),
        "summary_line": (
            f"Required editor targets: {'PASS' if total_count > 0 and ready_count >= total_count else 'CHECK'} | "
            f"match={ready_count}/{total_count}"
        ),
    }


def build_load_combination_diff_receipt(
    *,
    current_editor_seed: dict[str, Any],
    baseline_editor_seed: dict[str, Any],
    commercialization_target: Any = None,
    baseline_trace: dict[str, Any] | None = None,
    receipt_trace: dict[str, Any] | None = None,
    acceptance_reason: str | None = None,
    expansion_reason: str | None = None,
    allow_additive_inference: bool = False,
) -> dict[str, Any]:
    current_cases = set(_editor_seed_case_names(current_editor_seed))
    baseline_cases = set(_editor_seed_case_names(baseline_editor_seed))
    current_combos = {combo.name: combo for combo in _editor_seed_runtime_combinations(current_editor_seed)}
    baseline_combos = {combo.name: combo for combo in _editor_seed_runtime_combinations(baseline_editor_seed)}

    added_case_names = sorted(current_cases - baseline_cases)
    removed_case_names = sorted(baseline_cases - current_cases)
    added_combo_names = sorted(set(current_combos) - set(baseline_combos))
    removed_combo_names = sorted(set(baseline_combos) - set(current_combos))
    changed_combo_names = sorted(
        combo_name
        for combo_name in sorted(set(current_combos) & set(baseline_combos))
        if current_combos[combo_name].limit_state != baseline_combos[combo_name].limit_state
        or dict(current_combos[combo_name].factors) != dict(baseline_combos[combo_name].factors)
    )
    unchanged_combo_names = sorted(
        combo_name
        for combo_name in sorted(set(current_combos) & set(baseline_combos))
        if combo_name not in changed_combo_names
    )
    changed_combo_rows = [
        {
            "name": combo_name,
            "baseline_limit_state": str(baseline_combos[combo_name].limit_state),
            "current_limit_state": str(current_combos[combo_name].limit_state),
            "baseline_factor_map": {
                str(key): float(value)
                for key, value in sorted(baseline_combos[combo_name].factors.items())
            },
            "current_factor_map": {
                str(key): float(value)
                for key, value in sorted(current_combos[combo_name].factors.items())
            },
        }
        for combo_name in changed_combo_names
    ]

    def _factor_map_is_expansion(
        *,
        baseline_factor_map: dict[str, float],
        current_factor_map: dict[str, float],
    ) -> bool:
        if not set(baseline_factor_map).issubset(current_factor_map):
            return False
        for key, baseline_value in baseline_factor_map.items():
            current_value = float(current_factor_map.get(key, 0.0))
            baseline_value = float(baseline_value)
            if abs(baseline_value) <= 1.0e-12:
                continue
            if baseline_value * current_value < 0.0:
                return False
            if abs(current_value) + 1.0e-12 < abs(baseline_value):
                return False
        return True

    expanded_combo_names = sorted(
        combo_name
        for combo_name in changed_combo_names
        if current_combos[combo_name].limit_state == baseline_combos[combo_name].limit_state
        and _factor_map_is_expansion(
            baseline_factor_map=dict(baseline_combos[combo_name].factors),
            current_factor_map=dict(current_combos[combo_name].factors),
        )
    )
    total_differences = (
        len(added_case_names)
        + len(removed_case_names)
        + len(added_combo_names)
        + len(removed_combo_names)
        + len(changed_combo_names)
    )

    def _normalize_policy_token(value: Any) -> str:
        token = str(value or "").strip().lower()
        for needle in ("-", " ", "/", "."):
            token = token.replace(needle, "_")
        while "__" in token:
            token = token.replace("__", "_")
        return token.strip("_")

    def _policy_label(token: str) -> str:
        return token.replace("_", " ") if token else ""

    def _extract_target_mode(payload: Any) -> tuple[str, str, str, str]:
        if isinstance(payload, dict):
            for key in ("mode", "target", "value", "kind", "name", "policy", "status", "label"):
                token = _normalize_policy_token(payload.get(key))
                if token:
                    return (
                        token,
                        str(payload.get("source") or payload.get("origin") or f"explicit_{key}"),
                        str(payload.get("acceptance_reason") or payload.get("acceptanceReason") or ""),
                        str(
                            payload.get("expansion_reason")
                            or payload.get("expansionReason")
                            or payload.get("reason")
                            or ""
                        ),
                    )
            return ("", "", "", "")
        token = _normalize_policy_token(payload)
        source = "explicit_value" if token else ""
        return (token, source, "", "")

    def _normalize_trace(payload: dict[str, Any] | None) -> dict[str, Any]:
        normalized = dict(payload or {})
        ready = bool(normalized.get("ready", False))
        if not ready:
            for key in (
                "artifact_path",
                "payload_sha256",
                "reference",
                "family_id",
                "design_family",
                "session_id",
                "summary_line",
            ):
                if str(normalized.get(key, "") or "").strip():
                    ready = True
                    break
        normalized["ready"] = bool(ready)
        return normalized

    change_classification = "baseline_divergence"
    if total_differences == 0:
        change_classification = "exact_match"
    elif not removed_case_names and not removed_combo_names and not changed_combo_names:
        change_classification = "additive_expansion"
    elif (
        not removed_case_names
        and not removed_combo_names
        and len(expanded_combo_names) == len(changed_combo_names)
    ):
        change_classification = "baseline_preserving_expansion"

    target_mode, target_source, target_acceptance_reason, target_expansion_reason = _extract_target_mode(
        commercialization_target
    )
    if not target_mode and allow_additive_inference and change_classification in {
        "additive_expansion",
        "baseline_preserving_expansion",
    }:
        target_mode = "intentional_expansion"
        target_source = "inferred_baseline_preserving_expansion"
    intentional_expansion_target = target_mode in {
        "intentional_expansion",
        "intentional_additive_expansion",
        "additive_expansion",
    }
    baseline_traceability = _normalize_trace(baseline_trace)
    receipt_traceability = _normalize_trace(receipt_trace)
    traceability_ready = bool(baseline_traceability["ready"] and receipt_traceability["ready"])

    if change_classification == "exact_match":
        closure_status = "exact_family_baseline_match"
        contract_pass = True
    elif intentional_expansion_target and change_classification in {
        "additive_expansion",
        "baseline_preserving_expansion",
    } and traceability_ready:
        closure_status = "intentional_expansion_with_traceable_baseline_receipt"
        contract_pass = True
    elif intentional_expansion_target and change_classification in {
        "additive_expansion",
        "baseline_preserving_expansion",
    }:
        closure_status = "intentional_expansion_missing_traceability"
        contract_pass = False
    else:
        closure_status = "family_baseline_review_required"
        contract_pass = False

    acceptance_reason_text = str(acceptance_reason or "").strip() or target_acceptance_reason.strip()
    if not acceptance_reason_text:
        if change_classification == "exact_match":
            acceptance_reason_text = "Current load-combination editor seed matches the family baseline exactly."
        elif closure_status == "intentional_expansion_with_traceable_baseline_receipt":
            acceptance_reason_text = (
                "Current commercialization target is an intentional expansion and both the baseline and receipt "
                "remain traceable."
            )
        elif closure_status == "intentional_expansion_missing_traceability":
            acceptance_reason_text = (
                "Intentional expansion was identified, but the baseline or receipt trace needed to close the diff "
                "receipt is incomplete."
            )
        else:
            acceptance_reason_text = "Family baseline differences still require review before the diff receipt can close."

    expansion_reason_text = str(expansion_reason or "").strip() or target_expansion_reason.strip()
    if not expansion_reason_text:
        if change_classification == "exact_match":
            expansion_reason_text = "No expansion beyond the family baseline was detected."
        elif change_classification == "additive_expansion":
            expansion_reason_text = (
                "Baseline coverage stays intact while the current target adds "
                f"{len(added_case_names)} case(s) and {len(added_combo_names)} combination(s)."
            )
        elif change_classification == "baseline_preserving_expansion":
            expansion_reason_text = (
                "Baseline coverage stays intact while the current target adds "
                f"{len(added_case_names)} case(s), {len(added_combo_names)} combination(s), and expands "
                f"{len(expanded_combo_names)} existing combination(s)."
            )
        else:
            expansion_reason_text = (
                "Diff includes removals or changed baseline combinations "
                f"(removed_cases={len(removed_case_names)}, removed_combos={len(removed_combo_names)}, "
                f"changed_combos={len(changed_combo_names)})."
            )

    return {
        "added_case_names": added_case_names,
        "removed_case_names": removed_case_names,
        "added_combo_names": added_combo_names,
        "removed_combo_names": removed_combo_names,
        "changed_combo_names": changed_combo_names,
        "unchanged_combo_names": unchanged_combo_names,
        "changed_combo_rows": changed_combo_rows,
        "expanded_combo_names": expanded_combo_names,
        "change_classification": change_classification,
        "commercialization_target": {
            "value": target_mode,
            "label": _policy_label(target_mode),
            "source": target_source,
        },
        "traceability": {
            "ready": traceability_ready,
            "baseline": baseline_traceability,
            "receipt": receipt_traceability,
        },
        "closure_status": closure_status,
        "acceptance_reason": acceptance_reason_text,
        "expansion_reason": expansion_reason_text,
        "difference_count": int(total_differences),
        "contract_pass": contract_pass,
        "summary_line": (
            "Load diff receipt: "
            f"{'PASS' if contract_pass else 'CHECK'} | "
            f"policy={closure_status} | "
            f"target={target_mode or 'baseline_match'} | "
            f"cases(+/-)={len(added_case_names)}/{len(removed_case_names)} | "
            f"combos(+/-/~)={len(added_combo_names)}/{len(removed_combo_names)}/{len(changed_combo_names)}"
        ),
    }


def summarize_runtime_combination_model(model_payload: dict[str, Any]) -> dict[str, Any]:
    combo_rows = _load_combination_rows(model_payload)
    combo_lookup = _build_combo_row_lookup(combo_rows)
    name_to_refs: dict[str, tuple[str, ...]] = {}
    name_to_cases: dict[str, list[str]] = {}
    name_to_limit_state: dict[str, str] = {}
    case_refs: set[str] = set()
    unresolved_refs: set[str] = set()
    nested_combo_count = 0
    memo: dict[str, dict[str, float]] = {}

    for row in combo_rows:
        combo_name = str(row.get("name", "") or "").strip()
        if not combo_name:
            continue
        normalized_factor_map = _resolve_combo_factor_map(
            row,
            combo_lookup=combo_lookup,
            memo=memo,
            resolving=set(),
        )
        entry_rows = _editor_seed_entry_rows(row)
        nested_refs: list[str] = []
        for entry in entry_rows:
            reference_kind = str(entry.get("reference_kind", "")).strip().upper()
            reference_name = str(entry.get("reference_name", "")).strip()
            if not reference_name:
                continue
            if reference_kind == "CB":
                nested_refs.append(reference_name)
                if _lookup_combo_row(combo_lookup, reference_name) is None:
                    unresolved_refs.add(reference_name)
        if nested_refs:
            nested_combo_count += 1
        name_to_refs[combo_name] = tuple(sorted(set(nested_refs)))
        resolved_case_names = list(sorted(str(case_name) for case_name in normalized_factor_map.keys()))
        name_to_cases[combo_name] = resolved_case_names
        case_refs.update(resolved_case_names)
        name_to_limit_state[combo_name] = _normalized_limit_state_label(
            str(row.get("limit_state", "")).strip() or str(row.get("combination_type", "")).strip()
        )

    depth_memo: dict[str, int] = {}
    resolving: set[str] = set()

    def _depth(combo_name: str) -> int:
        if combo_name in depth_memo:
            return depth_memo[combo_name]
        if combo_name in resolving:
            return 0
        resolving.add(combo_name)
        try:
            refs = name_to_refs.get(combo_name, ())
            if not refs:
                depth_memo[combo_name] = 1
                return 1
            depth = 1 + max(_depth(ref) for ref in refs if ref in name_to_refs)
            depth_memo[combo_name] = depth
            return depth
        finally:
            resolving.discard(combo_name)

    combo_depth_rows: list[dict[str, Any]] = []
    combo_family_counts: dict[str, int] = {}
    family_tag_counts = {tag: 0 for tag in (*_CASE_FAMILY_ORDER, "nested", "other")}
    family_depth_max = {tag: 0 for tag in (*_CASE_FAMILY_ORDER, "nested")}
    limit_state_counts: dict[str, int] = {}
    for combo_name in sorted(name_to_refs):
        nested_reference_count = len(name_to_refs.get(combo_name, ()))
        nested_depth = _depth(combo_name)
        family_profile = _combo_case_family_profile(
            case_names=name_to_cases.get(combo_name, []),
            nested_reference_count=nested_reference_count,
            nested_depth=nested_depth,
        )
        family_label = str(family_profile.get("family_label", "other") or "other")
        combo_family_counts[family_label] = int(combo_family_counts.get(family_label, 0)) + 1
        for tag in family_profile.get("family_tags", []):
            tag_name = str(tag)
            family_tag_counts[tag_name] = int(family_tag_counts.get(tag_name, 0)) + 1
            if tag_name in family_depth_max:
                family_depth_max[tag_name] = max(int(family_depth_max.get(tag_name, 0)), int(nested_depth))
        limit_state = name_to_limit_state.get(combo_name, "UNSPECIFIED")
        limit_state_counts[limit_state] = int(limit_state_counts.get(limit_state, 0)) + 1
        combo_depth_rows.append(
            {
                "name": combo_name,
                "limit_state": limit_state,
                "nested_reference_count": nested_reference_count,
                "nested_depth": nested_depth,
                "case_count": int(family_profile.get("case_count", 0) or 0),
                "case_names": list(family_profile.get("case_names") or []),
                "family_label": family_label,
                "family_tags": list(family_profile.get("family_tags") or []),
                "rc_present": bool(family_profile.get("rc_present", False)),
                "wind_present": bool(family_profile.get("wind_present", False)),
                "seismic_present": bool(family_profile.get("seismic_present", False)),
                "nested_present": bool(family_profile.get("nested_present", False)),
            }
        )
    max_nested_depth = max((int(row["nested_depth"]) for row in combo_depth_rows), default=0)
    linear_combo_count = max(len(combo_depth_rows) - nested_combo_count, 0)
    runtime_case_family_counts = {
        "rc": int(sum(1 for case_name in case_refs if case_name in _RC_CASE_KEYS)),
        "wind": int(sum(1 for case_name in case_refs if case_name in _WIND_CASE_KEYS)),
        "seismic": int(sum(1 for case_name in case_refs if case_name in _SEISMIC_CASE_KEYS)),
    }
    runtime_case_breadth_labels = [
        tag for tag in _CASE_FAMILY_ORDER if int(runtime_case_family_counts.get(tag, 0)) > 0
    ]
    runtime_case_breadth_label = ", ".join(runtime_case_breadth_labels) if runtime_case_breadth_labels else "other"
    authoring_ready = bool(combo_depth_rows and not unresolved_refs)
    summary_line = (
        f"Runtime load-combination authoring: {'PASS' if authoring_ready else 'CHECK'} | "
        f"combos={len(combo_depth_rows)} | linear={linear_combo_count} | nested={nested_combo_count} | "
        f"max_depth={max_nested_depth} | cases={len(case_refs)} | breadth={runtime_case_breadth_label} | "
        f"rc/wind/seismic={family_tag_counts.get('rc', 0)}/{family_tag_counts.get('wind', 0)}/{family_tag_counts.get('seismic', 0)} | "
        f"unresolved={len(unresolved_refs)}"
    )
    return {
        "combo_count": int(len(combo_depth_rows)),
        "linear_combo_count": int(linear_combo_count),
        "nested_combo_count": int(nested_combo_count),
        "max_nested_depth": int(max_nested_depth),
        "runtime_case_count": int(len(case_refs)),
        "runtime_case_names": list(sorted(case_refs)),
        "runtime_case_family_counts": {str(key): int(value) for key, value in sorted(runtime_case_family_counts.items())},
        "runtime_case_breadth_count": int(len(runtime_case_breadth_labels)),
        "runtime_case_breadth_label": runtime_case_breadth_label,
        "combo_family_counts": {str(key): int(value) for key, value in sorted(combo_family_counts.items())},
        "family_tag_counts": {str(key): int(value) for key, value in sorted(family_tag_counts.items())},
        "limit_state_counts": {str(key): int(value) for key, value in sorted(limit_state_counts.items())},
        "rc_combo_count": int(family_tag_counts.get("rc", 0)),
        "wind_combo_count": int(family_tag_counts.get("wind", 0)),
        "seismic_combo_count": int(family_tag_counts.get("seismic", 0)),
        "rc_max_nested_depth": int(family_depth_max.get("rc", 0)),
        "wind_max_nested_depth": int(family_depth_max.get("wind", 0)),
        "seismic_max_nested_depth": int(family_depth_max.get("seismic", 0)),
        "unresolved_reference_count": int(len(unresolved_refs)),
        "unresolved_reference_names": list(sorted(unresolved_refs)),
        "combo_depth_rows": combo_depth_rows,
        "authoring_ready": bool(authoring_ready),
        "summary_line": summary_line,
    }


def _format_midas_factor(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return f"{number:.12g}"


def _sanitize_midas_description(value: str) -> str:
    text = " ".join(str(value or "").replace(",", " ").split()).strip()
    return text[:96] if text else "combination export preview"


def _chunk_sequence(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size <= 0:
        return [list(items)]
    return [items[index:index + size] for index in range(0, len(items), size)]


def _editor_seed_entry_rows(combo_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in (combo_row.get("entry_rows") or [])
        if isinstance(row, dict)
    ]
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        reference_kind = str(row.get("reference_kind", "")).strip().upper()
        reference_name = str(row.get("reference_name", "")).strip()
        if reference_kind not in {"ST", "CB"} or not reference_name:
            continue
        normalized_rows.append(
            {
                "reference_kind": reference_kind,
                "reference_name": reference_name,
                "factor": float(row.get("factor", 0.0) or 0.0),
            }
        )
    if normalized_rows:
        return normalized_rows

    referenced_combinations = [
        str(item).strip()
        for item in (combo_row.get("referenced_combinations") or [])
        if str(item).strip()
    ]
    if referenced_combinations:
        return [
            {
                "reference_kind": "CB",
                "reference_name": reference_name,
                "factor": 1.0,
            }
            for reference_name in referenced_combinations
        ]

    factor_map = combo_row.get("factor_map") if isinstance(combo_row.get("factor_map"), dict) else {}
    return [
        {
            "reference_kind": "ST",
            "reference_name": str(case_name).strip(),
            "factor": float(factor),
        }
        for case_name, factor in sorted(factor_map.items())
        if str(case_name).strip()
    ]


def _derive_midas_loadcomb_description(combo_row: dict[str, Any], entry_rows: list[dict[str, Any]]) -> str:
    expression = str(combo_row.get("expression", "") or "").strip()
    if expression and expression.lower() != "expression n/a":
        return _sanitize_midas_description(expression)
    referenced_combinations = [
        str(item).strip()
        for item in (combo_row.get("referenced_combinations") or [])
        if str(item).strip()
    ]
    if referenced_combinations:
        preview = " + ".join(referenced_combinations[:3])
        if len(referenced_combinations) > 3:
            preview = f"{preview} + {len(referenced_combinations) - 3} more"
        return _sanitize_midas_description(f"Envelope refs {preview}")
    referenced_cases = [
        str(row.get("reference_name", "")).strip()
        for row in entry_rows
        if str(row.get("reference_kind", "")).strip().upper() == "ST" and str(row.get("reference_name", "")).strip()
    ]
    if referenced_cases:
        preview = " + ".join(referenced_cases[:4])
        if len(referenced_cases) > 4:
            preview = f"{preview} + {len(referenced_cases) - 4} more"
        return _sanitize_midas_description(f"Linear refs {preview}")
    return _sanitize_midas_description(str(combo_row.get("name", "") or "combination export preview"))


def export_midas_loadcomb_from_editor_seed(
    editor_seed: dict[str, Any],
    *,
    include_comments: bool = True,
) -> str:
    if not isinstance(editor_seed, dict):
        return ""
    combination_nodes = [
        row
        for row in (editor_seed.get("combination_nodes") or [])
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]
    if not combination_nodes:
        return ""

    ordered_combinations = sorted(
        combination_nodes,
        key=lambda row: (
            int(row.get("editor_stage", 0) or 0),
            str(row.get("name", "") or ""),
        ),
    )
    lines = ["*LOADCOMB"]
    if include_comments:
        lines.append("; NAME=NAME, KIND, ACTIVE, bES, iTYPE, DESC, iSERV-TYPE, nLCOMTYPE, nSEISTYPE")
        lines.append(";      ANAL1, LCNAME1, FACT1, ...")
    for combo_row in ordered_combinations:
        name = str(combo_row.get("name", "") or "").strip()
        if not name:
            continue
        combination_type = str(combo_row.get("combination_type", "") or "GEN").strip() or "GEN"
        limit_state = str(combo_row.get("limit_state", "") or "ACTIVE").strip() or "ACTIVE"
        entry_rows = _editor_seed_entry_rows(combo_row)
        description = _derive_midas_loadcomb_description(combo_row, entry_rows)
        description_mode = 1 if any(str(row.get("reference_kind", "")).strip().upper() == "CB" for row in entry_rows) else 0
        lines.append(
            f"   NAME={name}, {combination_type}, {limit_state}, 0, {description_mode}, {description}, 0, 0, 0"
        )
        for chunk in _chunk_sequence(entry_rows, 2):
            tokens: list[str] = []
            for row in chunk:
                tokens.extend(
                    [
                        str(row.get("reference_kind", "")).strip().upper() or "ST",
                        str(row.get("reference_name", "")).strip(),
                        _format_midas_factor(row.get("factor", 0.0)),
                    ]
                )
            if tokens:
                lines.append("        " + ", ".join(tokens))
    return "\n".join(lines) + "\n"


def export_midas_loadcomb_from_model_payload(
    model_payload: dict[str, Any],
    *,
    include_comments: bool = True,
) -> str:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return ""
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    editor_seed = metadata.get("load_combination_editor_seed") if isinstance(metadata.get("load_combination_editor_seed"), dict) else {}
    if not editor_seed:
        derive_fn = None
        recover_fn = None
        try:
            from implementation.phase1.parse_midas_mgt_to_json_npz import (
                derive_load_combination_editor_seed_for_model_payload as derive_fn,
                derive_load_productization_from_raw_combination_payload as recover_fn,
            )
        except Exception:
            try:
                from parse_midas_mgt_to_json_npz import (
                    derive_load_combination_editor_seed_for_model_payload as derive_fn,
                    derive_load_productization_from_raw_combination_payload as recover_fn,
                )
            except Exception:
                derive_fn = None
                recover_fn = None
        if callable(derive_fn):
            try:
                editor_seed = derive_fn(model_payload)
            except Exception:
                editor_seed = {}
        if not editor_seed and callable(recover_fn):
            try:
                recovered = recover_fn(model_payload)
            except Exception:
                recovered = {}
            editor_seed = recovered.get("load_combination_editor_seed") if isinstance(recovered.get("load_combination_editor_seed"), dict) else {}
    return export_midas_loadcomb_from_editor_seed(editor_seed, include_comments=include_comments)


__all__ = [
    "LoadCombination",
    "KDS_CONCRETE_FAMILY",
    "KDS_GENERIC_GATE_FAMILY",
    "KDS_RC_BASIC_FAMILY",
    "KDS_RC_NESTED_FAMILY",
    "KDS_RC_NESTED_GATE_FAMILY",
    "KDS_RC_SEISMIC_FAMILY",
    "KDS_RC_SEISMIC_GATE_FAMILY",
    "KDS_RC_WIND_FAMILY",
    "KDS_RC_WIND_GATE_FAMILY",
    "KDS_STEEL_BASIC_FAMILY",
    "KDS_STEEL_GRAVITY_GATE_FAMILY",
    "build_load_combination_diff_receipt",
    "canonicalize_kds_family",
    "export_midas_loadcomb_from_editor_seed",
    "export_midas_loadcomb_from_model_payload",
    "generate_kds_steel_service_combinations",
    "generate_kds_steel_strength_combinations",
    "generate_kds_service_combinations",
    "generate_kds_strength_combinations",
    "generate_named_scale_library",
    "infer_combination_family_from_midas_model",
    "load_combinations_from_midas_model",
    "match_runtime_to_required_editor_targets",
    "match_runtime_to_kds",
    "normalize_runtime_case_name",
    "summarize_runtime_combination_model",
]
