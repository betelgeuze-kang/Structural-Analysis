from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


THIS_DIR = Path(__file__).resolve().parent
review_ui = _load_module(
    THIS_DIR / "generate_optimized_drawing_review_ui.py",
    "optimized_review_ui_batch_wrapper",
)
pdf_exporter = _load_module(
    THIS_DIR / "export_optimized_drawing_expert_review_pdf.py",
    "optimized_review_pdf_export_batch_wrapper",
)

DEFAULT_VIEWER_JSON = Path(review_ui.DEFAULT_VIEWER_JSON)
DEFAULT_EXPERT_REVIEW_METADATA_JSON = Path(pdf_exporter.DEFAULT_EXPERT_REVIEW_METADATA_JSON)
DEFAULT_EXPERT_METADATA_TEMPLATE_DIR = Path(review_ui.DEFAULT_EXPERT_METADATA_TEMPLATE_DIR)
DEFAULT_PROJECT_ONBOARDING_JSON = Path(review_ui.DEFAULT_EXPERT_METADATA_ONBOARDING_EXAMPLE)
DEFAULT_OUT_DIR = Path("implementation/phase1/release/visualization/expert_review_batch")
DEFAULT_OUT_MANIFEST_JSON = DEFAULT_OUT_DIR / "optimized_drawing_expert_review.batch_manifest.json"
DEFAULT_OUT_RECEIPT_TXT = DEFAULT_OUT_DIR / "optimized_drawing_expert_review.batch_receipt.txt"

COMMON_ONBOARDING_SECTIONS = ("project_identity", "review_team", "metadata_overrides")
API_COMMON_ONBOARDING_SECTIONS = ("project", "review_team", "metadata_overrides")
REQUIRED_API_SECTIONS = ("api_version", "request", "project", "submission", "review_team")
COMMON_SUBMISSION_CONTEXT_KEYS = {
    "issue_date",
    "package_id",
    "revision_code",
    "discipline_label",
    "code_basis",
}
REQUIRED_SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "request": ("request_id", "submitted_at", "submitted_by", "submission_channel", "template_name"),
    "project": ("project_name", "project_number", "client_name", "site_name"),
    "submission": (),
    "review_team": ("prepared_by", "reviewed_by"),
}
ALLOWED_SUBMISSION_CHANNELS = {"customer_portal", "sales_ops", "api_import"}


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _string_value(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _dict_section(payload: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        section = payload.get(name)
        if isinstance(section, dict):
            return section
    return {}


def _copy_string_fields(target: dict[str, Any], section_payload: dict[str, Any], *, keys: list[str] | None = None) -> None:
    iterable = keys if keys is not None else list(section_payload.keys())
    for key in iterable:
        text = _string_value(section_payload.get(key))
        if text:
            target[str(key)] = text


def _selected_template_name(project_onboarding_payload: dict[str, Any]) -> str:
    request = _dict_section(project_onboarding_payload, "request")
    selection = _dict_section(project_onboarding_payload, "template_selection")
    return _string_value(request.get("template_name")) or _string_value(selection.get("template_name"))


def _selection_reason(project_onboarding_payload: dict[str, Any]) -> str:
    request = _dict_section(project_onboarding_payload, "request")
    selection = _dict_section(project_onboarding_payload, "template_selection")
    return _string_value(request.get("selection_reason")) or _string_value(selection.get("selection_reason"))


def _onboarding_request_metadata(project_onboarding_payload: dict[str, Any]) -> dict[str, str]:
    request = _dict_section(project_onboarding_payload, "request")
    return {
        "api_version": _string_value(project_onboarding_payload.get("api_version")),
        "request_id": _string_value(request.get("request_id")),
        "submitted_at": _string_value(request.get("submitted_at")),
        "submitted_by": _string_value(request.get("submitted_by")),
        "submission_channel": _string_value(request.get("submission_channel")),
    }


def _onboarding_payload_kind(project_onboarding_payload: dict[str, Any]) -> str:
    if _dict_section(project_onboarding_payload, "request") and _dict_section(project_onboarding_payload, "project"):
        return "customer_portal_api_payload"
    if _dict_section(project_onboarding_payload, "template_selection") and _dict_section(project_onboarding_payload, "project_identity"):
        return "sectioned_onboarding_payload"
    return "flat_or_unknown_payload"


def _write_json_like_source(path: Path, payload: dict[str, Any], *, source_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if source_path and source_path.exists():
        path.write_bytes(source_path.read_bytes())
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _build_onboarding_intake_receipt(
    *,
    project_onboarding_payload: dict[str, Any],
    source_project_onboarding_json: Path | None,
    target_template_name: str,
    materialized_issue_metadata: dict[str, Any],
) -> dict[str, Any]:
    request_meta = _onboarding_request_metadata(project_onboarding_payload)
    payload_kind = _onboarding_payload_kind(project_onboarding_payload)
    present_sections = [
        key
        for key, value in project_onboarding_payload.items()
        if isinstance(value, dict) and value
    ]
    validation = _validate_project_onboarding_payload(project_onboarding_payload)
    return {
        "schema_version": "expert_review_onboarding_intake_receipt.v1",
        "payload_kind": payload_kind,
        "source_project_onboarding_json": str(source_project_onboarding_json) if source_project_onboarding_json else "",
        "target_template_name": str(target_template_name or ""),
        "selected_template_name": _selected_template_name(project_onboarding_payload),
        "selection_reason": _selection_reason(project_onboarding_payload),
        "request": request_meta,
        "present_sections": present_sections,
        "validation": validation,
        "missing_required_fields": list(validation.get("missing_required_fields") or []),
        "warnings": list(validation.get("warnings") or []),
        "materialized_issue_metadata_keys": sorted(materialized_issue_metadata.keys()),
        "template_sensitive_override_mode": str(
            materialized_issue_metadata.get("onboarding_template_sensitive_override_mode", "") or ""
        ),
    }


def _validate_project_onboarding_payload(project_onboarding_payload: dict[str, Any]) -> dict[str, Any]:
    missing_required_fields: list[str] = []
    warnings: list[str] = []
    checked_fields: list[str] = []
    payload_kind = _onboarding_payload_kind(project_onboarding_payload)
    api_version = _string_value(project_onboarding_payload.get("api_version"))

    if payload_kind == "customer_portal_api_payload":
        if api_version != "expert_review_onboarding_api.v1":
            missing_required_fields.append("api_version")
            warnings.append("api_version must be expert_review_onboarding_api.v1 for customer_portal_api_payload")
        else:
            checked_fields.append("api_version")

        for section_name in REQUIRED_API_SECTIONS[1:]:
            section_payload = _dict_section(project_onboarding_payload, section_name)
            if not section_payload:
                missing_required_fields.append(section_name)
                warnings.append(f"required section missing: {section_name}")
                continue
            checked_fields.append(section_name)
            for field_name in REQUIRED_SECTION_FIELDS.get(section_name, ()):
                value = _string_value(section_payload.get(field_name))
                if value:
                    checked_fields.append(f"{section_name}.{field_name}")
                else:
                    missing_required_fields.append(f"{section_name}.{field_name}")
                    warnings.append(f"required field missing: {section_name}.{field_name}")
        submission_channel = _string_value(_dict_section(project_onboarding_payload, "request").get("submission_channel"))
        if submission_channel and submission_channel not in ALLOWED_SUBMISSION_CHANNELS:
            warnings.append(
                "request.submission_channel should be one of "
                + ", ".join(sorted(ALLOWED_SUBMISSION_CHANNELS))
            )
        submitted_at = _string_value(_dict_section(project_onboarding_payload, "request").get("submitted_at"))
        if submitted_at and not submitted_at.endswith("Z"):
            warnings.append("request.submitted_at should be ISO-8601 UTC and end with 'Z'")
    elif payload_kind == "sectioned_onboarding_payload":
        warnings.append("legacy sectioned onboarding payload detected; customer_portal_api_payload is recommended")
        template_name = _selected_template_name(project_onboarding_payload)
        if template_name:
            checked_fields.append("template_selection.template_name")
        else:
            missing_required_fields.append("template_selection.template_name")
    else:
        warnings.append("payload did not match the expected onboarding API or legacy sectioned form contract")

    return {
        "status": "pass" if not missing_required_fields else "warn",
        "payload_kind": payload_kind,
        "checked_field_count": len(checked_fields),
        "checked_fields": checked_fields,
        "missing_required_fields": missing_required_fields,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def _flatten_project_onboarding(
    project_onboarding_payload: dict[str, Any],
    *,
    target_template_name: str,
) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    selected_template = _selected_template_name(project_onboarding_payload)
    selection_reason = _selection_reason(project_onboarding_payload)
    request_meta = _onboarding_request_metadata(project_onboarding_payload)

    payload_kind = _onboarding_payload_kind(project_onboarding_payload)
    for section_name in COMMON_ONBOARDING_SECTIONS:
        section_payload = project_onboarding_payload.get(section_name)
        if isinstance(section_payload, dict):
            _copy_string_fields(flattened, section_payload)
    for section_name in API_COMMON_ONBOARDING_SECTIONS:
        section_payload = project_onboarding_payload.get(section_name)
        if isinstance(section_payload, dict):
            _copy_string_fields(flattened, section_payload)

    submission_context = _dict_section(project_onboarding_payload, "submission_context", "submission")
    review_labels = _dict_section(project_onboarding_payload, "review_labels")
    reviewer_guidance = _dict_section(project_onboarding_payload, "reviewer_guidance")

    apply_template_sensitive_overrides = not selected_template or selected_template == str(target_template_name or "")
    _copy_string_fields(flattened, submission_context, keys=sorted(COMMON_SUBMISSION_CONTEXT_KEYS))
    if apply_template_sensitive_overrides:
        _copy_string_fields(
            flattened,
            submission_context,
            keys=[
                "authority_name",
                "permit_label",
                "committee_label",
                "package_purpose_label",
                "issue_phase_label",
                "revision_status",
            ],
        )
        _copy_string_fields(flattened, review_labels)
        _copy_string_fields(flattened, reviewer_guidance)

    if selected_template:
        flattened["onboarding_selected_template"] = selected_template
    if selection_reason:
        flattened["onboarding_selection_reason"] = selection_reason
    for request_key, target_key in [
        ("request_id", "onboarding_request_id"),
        ("submitted_at", "onboarding_submitted_at"),
        ("submitted_by", "onboarding_submitted_by"),
        ("submission_channel", "onboarding_submission_channel"),
        ("api_version", "onboarding_api_version"),
    ]:
        request_value = _string_value(request_meta.get(request_key))
        if request_value:
            flattened[target_key] = request_value
    flattened["onboarding_payload_kind"] = payload_kind
    if apply_template_sensitive_overrides:
        flattened["onboarding_template_sensitive_override_mode"] = "selected_template_labels_applied"
    else:
        flattened["onboarding_template_sensitive_override_mode"] = "template_defaults_preserved"
    return flattened


def export_expert_review_pdf_batch(
    *,
    expert_review_metadata_json: Path = DEFAULT_EXPERT_REVIEW_METADATA_JSON,
    out_dir: Path | None = None,
    out_manifest_json: Path | None = None,
    out_receipt_txt: Path | None = None,
    template_names: list[str] | tuple[str, ...] | None = None,
):
    return pdf_exporter.export_expert_review_pdf_batch(
        expert_review_metadata_json=expert_review_metadata_json,
        out_dir=out_dir,
        template_names=template_names,
        out_manifest_json=out_manifest_json,
        out_receipt_txt=out_receipt_txt,
    )


def export_rendered_expert_review_pdf_batch(
    *,
    viewer_json_path: Path = DEFAULT_VIEWER_JSON,
    project_onboarding_json: Path | None = None,
    expert_review_metadata_json: Path | None = None,
    expert_metadata_template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    out_manifest_json: Path = DEFAULT_OUT_MANIFEST_JSON,
    out_receipt_txt: Path = DEFAULT_OUT_RECEIPT_TXT,
    template_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    selected_templates = pdf_exporter._resolve_template_names(template_names)
    out_dir.mkdir(parents=True, exist_ok=True)

    project_onboarding_payload = _load_json(project_onboarding_json)
    source_metadata_payload = _load_json(expert_review_metadata_json)
    onboarding_selected_template = _selected_template_name(project_onboarding_payload)
    onboarding_selection_reason = _selection_reason(project_onboarding_payload)
    manifest_base_dir = out_manifest_json.parent
    template_rows: list[dict[str, Any]] = []

    for template_name in selected_templates:
        review_html_filename, expert_html_filename = pdf_exporter._template_html_filenames(template_name)
        review_html_path = out_dir / review_html_filename
        expert_html_path = out_dir / expert_html_filename
        summary_json_path = out_dir / f"optimized_drawing_review.{template_name}.summary.json"
        metadata_json_path = out_dir / pdf_exporter._template_metadata_filename(
            DEFAULT_EXPERT_REVIEW_METADATA_JSON,
            template_name,
        )
        pdf_path = out_dir / pdf_exporter._template_pdf_filename(
            DEFAULT_EXPERT_REVIEW_METADATA_JSON,
            template_name,
        )
        zip_path = out_dir / pdf_exporter._template_zip_filename(
            DEFAULT_EXPERT_REVIEW_METADATA_JSON,
            template_name,
        )
        onboarding_input_json_path = out_dir / f"project_onboarding.{template_name}.issue_metadata.json"
        onboarding_request_json_path = out_dir / f"project_onboarding.{template_name}.request.json"
        onboarding_receipt_json_path = out_dir / f"project_onboarding.{template_name}.intake_receipt.json"

        materialized_issue_metadata = dict(source_metadata_payload)
        materialized_issue_metadata.update(
            _flatten_project_onboarding(project_onboarding_payload, target_template_name=template_name)
        )
        _write_json_like_source(
            onboarding_request_json_path,
            project_onboarding_payload,
            source_path=project_onboarding_json,
        )
        _write_json(onboarding_input_json_path, materialized_issue_metadata)
        _write_json(
            onboarding_receipt_json_path,
            _build_onboarding_intake_receipt(
                project_onboarding_payload=project_onboarding_payload,
                source_project_onboarding_json=project_onboarding_json,
                target_template_name=template_name,
                materialized_issue_metadata=materialized_issue_metadata,
            ),
        )
        onboarding_receipt_payload = _load_json(onboarding_receipt_json_path)

        summary_payload = review_ui.write_review_artifacts(
            viewer_json_path=viewer_json_path,
            out_html=review_html_path,
            out_expert_html=expert_html_path,
            expert_metadata_json_path=onboarding_input_json_path,
            expert_metadata_template=template_name,
            expert_metadata_template_dir=expert_metadata_template_dir,
            out_expert_metadata_json=metadata_json_path,
            out_summary=summary_json_path,
        )
        pdf_receipt = pdf_exporter.export_expert_review_pdf(
            expert_review_metadata_json=metadata_json_path,
            out_pdf=pdf_path,
            template_name=template_name,
        )
        zip_entries = pdf_exporter._write_deterministic_zip(
            zip_path,
            entries=[
                ("optimized_drawing_review.html", review_html_path),
                ("optimized_drawing_expert_review.html", expert_html_path),
                ("optimized_drawing_expert_review.metadata.json", metadata_json_path),
                ("optimized_drawing_expert_review.pdf", pdf_path),
                ("project_onboarding.request.json", onboarding_request_json_path),
                ("project_onboarding.intake_receipt.json", onboarding_receipt_json_path),
            ],
        )
        template_rows.append(
            {
                "template_name": template_name,
                "template_label": str(pdf_receipt.get("template_label", "") or template_name),
                "output_review_html": str(review_html_path),
                "relative_review_html": pdf_exporter._manifest_relpath(review_html_path, base_dir=manifest_base_dir),
                "output_expert_html": str(expert_html_path),
                "relative_expert_html": pdf_exporter._manifest_relpath(expert_html_path, base_dir=manifest_base_dir),
                "output_summary_json": str(summary_json_path),
                "relative_summary_json": pdf_exporter._manifest_relpath(summary_json_path, base_dir=manifest_base_dir),
                "output_metadata_json": str(metadata_json_path),
                "relative_metadata_json": pdf_exporter._manifest_relpath(metadata_json_path, base_dir=manifest_base_dir),
                "output_onboarding_request_json": str(onboarding_request_json_path),
                "relative_onboarding_request_json": pdf_exporter._manifest_relpath(
                    onboarding_request_json_path,
                    base_dir=manifest_base_dir,
                ),
                "output_onboarding_intake_receipt_json": str(onboarding_receipt_json_path),
                "relative_onboarding_intake_receipt_json": pdf_exporter._manifest_relpath(
                    onboarding_receipt_json_path,
                    base_dir=manifest_base_dir,
                ),
                "input_onboarding_issue_metadata_json": str(onboarding_input_json_path),
                "relative_input_onboarding_issue_metadata_json": pdf_exporter._manifest_relpath(
                    onboarding_input_json_path,
                    base_dir=manifest_base_dir,
                ),
                "out_pdf": str(pdf_path),
                "relative_pdf": pdf_exporter._manifest_relpath(pdf_path, base_dir=manifest_base_dir),
                "submission_zip": str(zip_path),
                "relative_submission_zip": pdf_exporter._manifest_relpath(zip_path, base_dir=manifest_base_dir),
                "zip_entry_count": len(zip_entries),
                "zip_sha256": pdf_exporter._deterministic_file_sha256(zip_path),
                "zip_entries": [
                    {
                        "arcname": str(entry.get("arcname", "") or ""),
                        "size_bytes": int(entry.get("size_bytes", 0) or 0),
                        "sha256": str(entry.get("sha256", "") or ""),
                    }
                    for entry in zip_entries
                    if isinstance(entry, dict)
                ],
                "page_count": int(pdf_receipt.get("page_count", 0) or 0),
                "issue_id": str(pdf_receipt.get("issue_id", "") or ""),
                "authority_name": str(pdf_receipt.get("authority_name", "") or ""),
                "package_purpose_label": str(pdf_receipt.get("package_purpose_label", "") or ""),
                "revision_code": str(pdf_receipt.get("revision_code", "") or ""),
                "metadata_source_mode": str(summary_payload.get("expert_review_metadata_source_mode", "") or ""),
                "metadata_template": str(summary_payload.get("expert_review_metadata_template", "") or ""),
                "template_selection_receipt": str(
                    summary_payload.get("expert_review_metadata_template_selection_receipt", "") or ""
                ),
                "onboarding_payload_kind": str(materialized_issue_metadata.get("onboarding_payload_kind", "") or ""),
                "onboarding_request_id": str(materialized_issue_metadata.get("onboarding_request_id", "") or ""),
                "intake_validation_status": str(
                    ((onboarding_receipt_payload.get("validation") or {}) if isinstance(onboarding_receipt_payload, dict) else {}).get("status", "") or ""
                ),
                "intake_warning_count": int(
                    ((onboarding_receipt_payload.get("validation") or {}) if isinstance(onboarding_receipt_payload, dict) else {}).get("warning_count", 0) or 0
                ),
                "intake_missing_required_field_count": len(
                    list(onboarding_receipt_payload.get("missing_required_fields") or [])
                ) if isinstance(onboarding_receipt_payload, dict) else 0,
            }
        )

    manifest_payload = {
        "schema_version": "optimized_drawing_expert_review_pdf.rendered_batch_manifest.v1",
        "render_mode": "viewer_json_template_render",
        "source_viewer_json": str(viewer_json_path),
        "source_project_onboarding_json": str(project_onboarding_json) if project_onboarding_json else "",
        "source_expert_review_metadata_json": str(expert_review_metadata_json) if expert_review_metadata_json else "",
        "template_dir": str(expert_metadata_template_dir),
        "template_order": selected_templates,
        "template_count": len(selected_templates),
        "zip_bundle_count": len(selected_templates),
        "onboarding_selected_template": onboarding_selected_template,
        "onboarding_selection_reason": onboarding_selection_reason,
        "output_dir": str(out_dir),
        "receipt_txt": str(out_receipt_txt),
        "templates": template_rows,
    }
    out_manifest_json.parent.mkdir(parents=True, exist_ok=True)
    out_manifest_json.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    receipt_lines = [
        "optimized_drawing_expert_review_pdf_batch_rendered",
        f"source_viewer_json={viewer_json_path}",
        f"source_project_onboarding_json={project_onboarding_json if project_onboarding_json else ''}",
        f"source_expert_review_metadata_json={expert_review_metadata_json if expert_review_metadata_json else ''}",
        f"template_dir={expert_metadata_template_dir}",
        f"manifest_json={out_manifest_json}",
        f"zip_bundle_count={len(selected_templates)}",
        f"template_order={','.join(selected_templates)}",
    ]
    if onboarding_selected_template:
        receipt_lines.append(f"onboarding_selected_template={onboarding_selected_template}")
    if onboarding_selection_reason:
        receipt_lines.append(f"onboarding_selection_reason={onboarding_selection_reason}")
    receipt_lines.extend(
        (
            f"{row['template_name']} | label={row['template_label']} | html={row['relative_expert_html']} | "
            f"summary={row['relative_summary_json']} | metadata={row['relative_metadata_json']} | "
            f"pdf={row['relative_pdf']} | zip={row['relative_submission_zip']} | "
            f"request={row['relative_onboarding_request_json']} | intake={row['relative_onboarding_intake_receipt_json']} | "
            f"issue={row['issue_id']} | authority={row['authority_name']} | package={row['package_purpose_label']} | "
            f"validation={row['intake_validation_status']} | warnings={row['intake_warning_count']} | missing={row['intake_missing_required_field_count']}"
        )
        for row in template_rows
    )
    out_receipt_txt.write_text("\n".join(receipt_lines) + "\n", encoding="utf-8")

    return {
        "manifest_json": str(out_manifest_json),
        "receipt_txt": str(out_receipt_txt),
        "output_dir": str(out_dir),
        "template_order": selected_templates,
        "template_count": len(selected_templates),
        "zip_bundle_count": len(selected_templates),
        "templates": template_rows,
        "source_project_onboarding_json": str(project_onboarding_json) if project_onboarding_json else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--viewer-json", default="")
    parser.add_argument("--project-onboarding-json", default="")
    parser.add_argument("--expert-review-metadata-json", default="")
    parser.add_argument("--template-dir", default=str(DEFAULT_EXPERT_METADATA_TEMPLATE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--out-manifest-json", default=str(DEFAULT_OUT_MANIFEST_JSON))
    parser.add_argument("--out-receipt-txt", default=str(DEFAULT_OUT_RECEIPT_TXT))
    parser.add_argument("--template", action="append", default=[])
    args = parser.parse_args()

    viewer_json_text = str(args.viewer_json).strip()
    onboarding_json_text = str(args.project_onboarding_json).strip()
    metadata_json_text = str(args.expert_review_metadata_json).strip()
    if onboarding_json_text or viewer_json_text:
        export_rendered_expert_review_pdf_batch(
            viewer_json_path=Path(viewer_json_text) if viewer_json_text else DEFAULT_VIEWER_JSON,
            project_onboarding_json=Path(onboarding_json_text) if onboarding_json_text else None,
            expert_review_metadata_json=Path(metadata_json_text) if metadata_json_text else None,
            expert_metadata_template_dir=Path(args.template_dir),
            out_dir=Path(args.out_dir),
            out_manifest_json=Path(args.out_manifest_json),
            out_receipt_txt=Path(args.out_receipt_txt),
            template_names=[str(value).strip() for value in (args.template or []) if str(value).strip()],
        )
        return

    export_expert_review_pdf_batch(
        expert_review_metadata_json=Path(metadata_json_text) if metadata_json_text else DEFAULT_EXPERT_REVIEW_METADATA_JSON,
        out_dir=Path(args.out_dir) if str(args.out_dir).strip() else None,
        out_manifest_json=Path(args.out_manifest_json) if str(args.out_manifest_json).strip() else None,
        out_receipt_txt=Path(args.out_receipt_txt) if str(args.out_receipt_txt).strip() else None,
        template_names=[str(value).strip() for value in (args.template or []) if str(value).strip()],
    )


if __name__ == "__main__":
    main()
