#!/usr/bin/env python3
"""Apply the scoped #136 deterministic concrete artifact source patch."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_phase2_state_updated_concrete_damage_artifacts.py"


def main() -> int:
    text = BUILDER.read_text(encoding="utf-8")
    text = text.replace(
        "import argparse\nfrom datetime import datetime, timezone\n",
        "import argparse\nfrom dataclasses import replace\nfrom datetime import datetime, timezone\n",
        1,
    )
    constants = (
        "STRUCTURE_LOAD_FACTORS = "
        "(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)\n"
    )
    replacement = (
        constants
        + 'LOCALIZATION_TIE_BREAK_PROFILE = "first_element_area_imperfection.v1"\n'
        + "LOCALIZATION_AREA_IMPERFECTION_RATIO = 1.0e-6\n"
    )
    if "LOCALIZATION_TIE_BREAK_PROFILE" not in text:
        text = text.replace(constants, replacement, 1)
    text = text.replace(
        '"seed at material-point, one-element, and two-element displacement-controlled "\n'
        '    "axial-chain scope. It records irreversible tension/compression damage, "',
        '"seed at material-point, one-element, and two-element displacement-controlled "\n'
        '    "axial-chain scope. The two-element counter-example uses a versioned "\n'
        '    "first-element area imperfection solely to select one of two symmetric "\n'
        '    "localization branches deterministically. It records irreversible "\n'
        '    "tension/compression damage, "',
        1,
    )
    strip_block = '''def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


'''
    diagnostic_block = '''def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _json_differences(
    existing: Any,
    expected: Any,
    path: str = "$",
) -> list[dict[str, Any]]:
    if type(existing) is not type(expected):
        return [
            {
                "path": path,
                "existing": existing,
                "expected": expected,
                "kind": "type",
            }
        ]
    if isinstance(existing, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(existing) | set(expected)):
            child = f"{path}.{key}"
            if key not in existing:
                rows.append(
                    {
                        "path": child,
                        "existing": "<missing>",
                        "expected": expected[key],
                        "kind": "missing_existing",
                    }
                )
            elif key not in expected:
                rows.append(
                    {
                        "path": child,
                        "existing": existing[key],
                        "expected": "<missing>",
                        "kind": "missing_expected",
                    }
                )
            else:
                rows.extend(_json_differences(existing[key], expected[key], child))
        return rows
    if isinstance(existing, list):
        rows = []
        if len(existing) != len(expected):
            rows.append(
                {
                    "path": f"{path}.length",
                    "existing": len(existing),
                    "expected": len(expected),
                    "kind": "length",
                }
            )
        for index, (left, right) in enumerate(zip(existing, expected, strict=False)):
            rows.extend(_json_differences(left, right, f"{path}[{index}]"))
        return rows
    signed_zero = bool(
        isinstance(existing, float)
        and isinstance(expected, float)
        and existing == expected == 0.0
        and bool(np.signbit(existing)) != bool(np.signbit(expected))
    )
    if existing != expected or signed_zero:
        row = {
            "path": path,
            "existing": existing,
            "expected": expected,
            "kind": "signed_zero" if signed_zero else "value",
        }
        if (
            isinstance(existing, (int, float))
            and not isinstance(existing, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool)
        ):
            row["absolute_difference"] = abs(float(existing) - float(expected))
        return [row]
    return []


def _difference_diagnostic(existing: Any, expected: Any) -> dict[str, Any]:
    rows = _json_differences(_strip_volatile(existing), _strip_volatile(expected))
    absolute = [
        float(row["absolute_difference"])
        for row in rows
        if "absolute_difference" in row
    ]
    return {
        "difference_count": len(rows),
        "first_difference": rows[0] if rows else None,
        "maximum_float_absolute_difference": max(absolute, default=0.0),
        "signed_zero_difference_count": sum(
            row["kind"] == "signed_zero" for row in rows
        ),
    }


'''
    if "def _json_differences" not in text:
        text = text.replace(strip_block, diagnostic_block, 1)
    old_problem = (
        "    structure_problem = "
        "two_element_concrete_damage_chain_problem(material=material)\n"
    )
    new_problem = '''    symmetric_structure_problem = two_element_concrete_damage_chain_problem(
        material=material
    )
    weakened_element = replace(
        symmetric_structure_problem.elements[0],
        area_m2=(
            symmetric_structure_problem.elements[0].area_m2
            * (1.0 - LOCALIZATION_AREA_IMPERFECTION_RATIO)
        ),
    )
    structure_problem = replace(
        symmetric_structure_problem,
        case_id=(
            "phase2_state_updated_concrete_damage_two_element_chain_"
            "imperfection_v1"
        ),
        elements=(weakened_element, symmetric_structure_problem.elements[1]),
    )
'''
    if old_problem in text:
        text = text.replace(old_problem, new_problem, 1)
    final_damage_block = '''    final_damage = [
        state.compressive_damage for state in structure_path.final_state.material_states
    ]
    localization_observed = bool(
'''
    final_damage_replacement = '''    final_damage = [
        state.compressive_damage for state in structure_path.final_state.material_states
    ]
    selected_localization_index = int(np.argmax(np.asarray(final_damage, dtype=float)))
    selected_localization_element_id = structure_problem.elements[
        selected_localization_index
    ].element_id
    deterministic_branch_selected = bool(
        selected_localization_element_id == "bar-1"
        and final_damage[0] > final_damage[1]
    )
    localization_observed = bool(
'''
    if "selected_localization_element_id" not in text:
        text = text.replace(final_damage_block, final_damage_replacement, 1)
    text = text.replace(
        "        and localization_observed\n    )\n",
        "        and localization_observed\n"
        "        and deterministic_branch_selected\n"
        "    )\n",
        1,
    )
    result_anchor = (
        '            "localization_observed": localization_observed,\n'
        '            "final_element_strains": final_strains,\n'
    )
    result_replacement = '''            "localization_observed": localization_observed,
            "localization_tie_break": {
                "profile": LOCALIZATION_TIE_BREAK_PROFILE,
                "area_imperfection_ratio": LOCALIZATION_AREA_IMPERFECTION_RATIO,
                "weakened_element_id": "bar-1",
                "selected_localization_element_id": (
                    selected_localization_element_id
                ),
                "deterministic_branch_selected": deterministic_branch_selected,
            },
            "final_element_strains": final_strains,
'''
    if '"localization_tie_break"' not in text:
        text = text.replace(result_anchor, result_replacement, 1)
    summary_anchor = (
        '        "localization_observed": localization_observed,\n'
        '        "mesh_objectivity_claim": False,\n'
    )
    summary_replacement = '''        "localization_observed": localization_observed,
        "localization_tie_break_profile": LOCALIZATION_TIE_BREAK_PROFILE,
        "localization_area_imperfection_ratio": (
            LOCALIZATION_AREA_IMPERFECTION_RATIO
        ),
        "selected_localization_element_id": selected_localization_element_id,
        "mesh_objectivity_claim": False,
'''
    if '"localization_tie_break_profile"' not in text:
        text = text.replace(summary_anchor, summary_replacement, 1)
    text = text.replace(
        '''        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_state_updated_concrete_damage_mismatch:{key}"
''',
        '''        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            diagnostic = _difference_diagnostic(existing, expected[key])
            diagnostic_text = json.dumps(
                diagnostic,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            return False, (
                f"phase2_state_updated_concrete_damage_mismatch:{key}:"
                f"{diagnostic_text}"
            )
''',
        1,
    )
    BUILDER.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
