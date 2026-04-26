"""Shared appendix helpers for design-optimization entrypoint summaries."""

from __future__ import annotations

from typing import Any


def annotate_entrypoint_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in groups:
        entrypoint_count = int(row.get("entrypoint_count", 0))
        pass_count = int(row.get("pass_count", 0))
        annotated.append(
            {
                **row,
                "fail_count": max(entrypoint_count - pass_count, 0),
            }
        )
    return annotated


def reason_distribution_text(rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("reason_code", "") or "unknown")
        counts[key] = int(counts.get(key, 0)) + 1
    return ", ".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "none"


def build_entrypoint_detail_groups(
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("group", "") or "")
        buckets.setdefault(key, []).append(row)
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_group in annotate_entrypoint_groups(groups):
        key = str(raw_group.get("group", "") or "")
        group_rows = list(buckets.get(key, []))
        ordered.append(
            {
                **raw_group,
                "rows": group_rows,
                "reason_distribution": reason_distribution_text(group_rows),
            }
        )
        seen.add(key)
    for key, bucket in buckets.items():
        if key in seen:
            continue
        ordered.append(
            {
                "group": key,
                "group_label": key or "Ungrouped",
                "report_count": len(bucket),
                "entrypoint_count": len(bucket),
                "pass_count": sum(1 for row in bucket if bool(row.get("contract_pass", False))),
                "fail_count": sum(1 for row in bucket if not bool(row.get("contract_pass", False))),
                "all_pass": all(bool(row.get("contract_pass", False)) for row in bucket) if bucket else False,
                "rows": list(bucket),
                "reason_distribution": reason_distribution_text(bucket),
            }
        )
    return ordered


def render_entrypoint_markdown_group_lines(
    groups: list[dict[str, Any]],
    *,
    include_members: bool,
) -> list[str]:
    lines: list[str] = []
    for row in annotate_entrypoint_groups(groups):
        line = (
            f"- `{row['group_label']}` reports=`{row['report_count']}/{row['entrypoint_count']}` "
            f"pass=`{row['pass_count']}` fail=`{row['fail_count']}` all_pass=`{row['all_pass']}`"
        )
        if include_members:
            line += f" members=`{', '.join(row.get('entrypoint_names', []))}`"
        lines.append(line)
    return lines


def render_entrypoint_markdown_appendix_lines(
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    for group in build_entrypoint_detail_groups(rows, groups):
        group_rows = list(group.get("rows", []))
        lines.extend(
            [
                "<details>",
                (
                    f"<summary>{group['group_label']} ({len(group_rows)} rows, "
                    f"pass={int(group.get('pass_count', 0))}, fail={int(group.get('fail_count', 0))}, "
                    f"reasons={group.get('reason_distribution', 'none')})</summary>"
                ),
                "",
            ]
        )
        lines.extend(
            [
                f"- `{row['name']}` group=`{row['group_label']}` pass=`{row['contract_pass']}` "
                f"reason=`{row['reason_code']}` | report=`{row['primary_report']}`"
                for row in group_rows
            ]
        )
        lines.extend(["", "</details>", ""])
    return lines


def render_entrypoint_markdown_sections(
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    include_members: bool,
    group_heading: str = "## Design Optimization Entrypoint Groups",
    appendix_heading: str = "## Appendix: Design Optimization Entrypoint Details",
) -> list[str]:
    annotated_groups = annotate_entrypoint_groups(groups)
    lines = [group_heading, ""]
    lines.extend(render_entrypoint_markdown_group_lines(annotated_groups, include_members=include_members))
    lines.extend(["", appendix_heading, ""])
    lines.extend(render_entrypoint_markdown_appendix_lines(rows, annotated_groups))
    return lines


def render_entrypoint_html_detail_sections(
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    table_style: str,
    header_html: str,
) -> str:
    sections: list[str] = []
    for group in build_entrypoint_detail_groups(rows, groups):
        group_rows = list(group.get("rows", []))
        row_html = "".join(
            f"<tr><td>{row['name']}</td><td>{row['group_label']}</td><td>{row['primary_report']}</td><td>{row['contract_pass']}</td><td>{row['reason_code']}</td></tr>"
            for row in group_rows
        )
        sections.append(
            f"""
        <details>
          <summary>{group['group_label']} ({len(group_rows)} rows, pass={int(group.get('pass_count', 0))}, fail={int(group.get('fail_count', 0))}, reasons={group.get('reason_distribution', 'none')})</summary>
          <table style="{table_style}">
            {header_html}
            <tbody>
              {row_html}
            </tbody>
          </table>
        </details>
        """
        )
    return "".join(sections)


__all__ = [
    "annotate_entrypoint_groups",
    "build_entrypoint_detail_groups",
    "reason_distribution_text",
    "render_entrypoint_html_detail_sections",
    "render_entrypoint_markdown_appendix_lines",
    "render_entrypoint_markdown_group_lines",
    "render_entrypoint_markdown_sections",
]
