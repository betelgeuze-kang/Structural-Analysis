from __future__ import annotations

from collections.abc import Iterable, Mapping
import html
from typing import Any


def _quote_char(quote: str) -> str:
    return '"' if quote == '"' else "'"


def _render_attrs(attrs: Mapping[str, Any] | None, quote: str) -> str:
    if not attrs:
        return ""
    parts: list[str] = []
    for key, value in attrs.items():
        if value is None or value is False:
            continue
        attr_name = html.escape(str(key), quote=True)
        if value is True:
            parts.append(f" {attr_name}")
            continue
        parts.append(f" {attr_name}={quote}{html.escape(str(value), quote=True)}{quote}")
    return "".join(parts)


def _render_class_attr(class_name: str, quote: str) -> str:
    normalized = " ".join(part for part in str(class_name).split() if part)
    if not normalized:
        return ""
    return f" class={quote}{html.escape(normalized, quote=True)}{quote}"


def render_route_context_banner(
    *,
    return_href: str = "../../../../index.html",
    return_label: str = "Structural Optimization Workbench",
    quote: str = "'",
) -> str:
    q = _quote_char(quote)
    href = html.escape(str(return_href), quote=True)
    label = html.escape(str(return_label))
    return (
        f"<div class={q}route-context-banner{q} id={q}route-context-banner{q} hidden>\n"
        f"  <div class={q}route-context-banner__eyebrow{q}>Connected Review Route</div>\n"
        f"  <div class={q}route-context-banner__title{q} id={q}route-context-title{q}></div>\n"
        f"  <div class={q}route-context-banner__meta{q}>\n"
        f"    <span id={q}route-context-step{q} hidden></span>\n"
        f"    <span id={q}route-context-source{q} hidden></span>\n"
        f"    <span id={q}route-context-target{q} hidden></span>\n"
        f"    <span id={q}route-context-status{q} hidden></span>\n"
        f"  </div>\n"
        f"  <div class={q}route-context-banner__note{q}>\n"
        f"    <span id={q}route-context-note{q} hidden></span>\n"
        f"    <a class={q}route-context-banner__return{q} id={q}route-context-return{q} href={q}{href}{q} hidden>{label}</a>\n"
        f"  </div>\n"
        f"</div>"
    )


def render_split_hero(
    *,
    main_markup: str,
    side_markup: str,
    section_id: str = "",
    section_class: str = "hero",
    main_tag: str = "div",
    main_classes: str = "hero-main",
    side_tag: str = "div",
    side_classes: str = "hero-side",
    quote: str = "'",
) -> str:
    q = _quote_char(quote)
    section_id_attr = f" id={q}{html.escape(section_id, quote=True)}{q}" if section_id else ""
    section_class_attr = html.escape(section_class, quote=True)
    main_class_attr = html.escape(main_classes, quote=True)
    side_class_attr = html.escape(side_classes, quote=True)
    return (
        f"<section class={q}{section_class_attr}{q}{section_id_attr}>\n"
        f"  <{main_tag} class={q}{main_class_attr}{q}>\n"
        f"{main_markup}\n"
        f"  </{main_tag}>\n"
        f"  <{side_tag} class={q}{side_class_attr}{q}>\n"
        f"{side_markup}\n"
        f"  </{side_tag}>\n"
        f"</section>"
    )


def render_section_heading(
    *,
    eyebrow: str = "",
    title: str = "",
    lead: str = "",
    shell_tag: str = "div",
    shell_class: str = "section-heading",
    body_tag: str = "div",
    body_class: str = "section-heading__body",
    eyebrow_tag: str = "div",
    eyebrow_class: str = "section-heading__eyebrow",
    title_tag: str = "h2",
    title_class: str = "section-heading__title",
    lead_tag: str = "p",
    lead_class: str = "section-heading__lead",
    actions_markup: str = "",
    actions_tag: str = "div",
    actions_class: str = "section-heading__actions",
    quote: str = "'",
) -> str:
    q = _quote_char(quote)
    body_parts: list[str] = []
    if eyebrow:
        body_parts.append(
            f"<{eyebrow_tag}{_render_class_attr(eyebrow_class, q)}>{eyebrow}</{eyebrow_tag}>"
        )
    if title:
        body_parts.append(
            f"<{title_tag}{_render_class_attr(title_class, q)}>{title}</{title_tag}>"
        )
    if lead:
        body_parts.append(
            f"<{lead_tag}{_render_class_attr(lead_class, q)}>{lead}</{lead_tag}>"
        )
    if not body_parts and not actions_markup:
        return ""
    actions_html = (
        f"<{actions_tag}{_render_class_attr(actions_class, q)}>{actions_markup}</{actions_tag}>"
        if actions_markup
        else ""
    )
    return (
        f"<{shell_tag}{_render_class_attr(shell_class, q)}>"
        f"<{body_tag}{_render_class_attr(body_class, q)}>{''.join(body_parts)}</{body_tag}>"
        f"{actions_html}</{shell_tag}>"
    )


def render_card_title_block(
    *,
    kicker: str = "",
    title: str = "",
    copy: str = "",
    shell_tag: str = "div",
    shell_class: str = "card-title-block",
    kicker_tag: str = "div",
    kicker_class: str = "card-title-block__kicker",
    title_tag: str = "h3",
    title_class: str = "card-title-block__title",
    copy_tag: str = "p",
    copy_class: str = "card-title-block__copy",
    actions_markup: str = "",
    actions_tag: str = "div",
    actions_class: str = "card-title-block__actions",
    quote: str = "'",
) -> str:
    q = _quote_char(quote)
    parts: list[str] = []
    if kicker:
        parts.append(f"<{kicker_tag}{_render_class_attr(kicker_class, q)}>{kicker}</{kicker_tag}>")
    if title:
        parts.append(f"<{title_tag}{_render_class_attr(title_class, q)}>{title}</{title_tag}>")
    if copy:
        parts.append(f"<{copy_tag}{_render_class_attr(copy_class, q)}>{copy}</{copy_tag}>")
    if actions_markup:
        parts.append(f"<{actions_tag}{_render_class_attr(actions_class, q)}>{actions_markup}</{actions_tag}>")
    if not parts:
        return ""
    return f"<{shell_tag}{_render_class_attr(shell_class, q)}>{''.join(parts)}</{shell_tag}>"


def render_token_row(
    *,
    items: Iterable[str | Mapping[str, Any] | None],
    container_class: str,
    item_class: str = "",
    container_tag: str = "div",
    item_tag: str = "span",
    container_attrs: Mapping[str, Any] | None = None,
    quote: str = "'",
    separator: str = "",
) -> str:
    q = _quote_char(quote)
    rendered_items: list[str] = []
    for item in items:
        if item is None:
            continue
        current_tag = item_tag
        current_class_name = item_class
        current_attrs: Mapping[str, Any] | None = None
        current_content = str(item)
        if isinstance(item, Mapping):
            current_content = str(item.get("content", "") or "")
            if not current_content:
                continue
            current_tag = str(item.get("tag", item_tag) or item_tag)
            current_class_name = " ".join(
                part for part in (item_class, str(item.get("class_name", "") or "")) if part
            )
            attrs_candidate = item.get("attrs")
            if isinstance(attrs_candidate, Mapping):
                current_attrs = {key: value for key, value in attrs_candidate.items() if str(key) != "class"}
        if not current_content:
            continue
        rendered_items.append(
            f"<{current_tag}"
            f"{_render_class_attr(current_class_name, q)}"
            f"{_render_attrs(current_attrs, q)}>"
            f"{current_content}</{current_tag}>"
        )
    if not rendered_items:
        return ""
    return (
        f"<{container_tag}"
        f"{_render_class_attr(container_class, q)}"
        f"{_render_attrs(container_attrs, q)}>"
        f"{separator.join(rendered_items)}</{container_tag}>"
    )


def render_link_pills(
    *,
    links: Iterable[tuple[str, str] | Mapping[str, Any] | None],
    link_class: str = "link-pill",
    container_class: str = "",
    container_tag: str = "div",
    container_attrs: Mapping[str, Any] | None = None,
    quote: str = "'",
    separator: str = "",
) -> str:
    q = _quote_char(quote)
    rendered_links: list[str] = []
    for link in links:
        if link is None:
            continue
        label = ""
        label_html = ""
        href = ""
        current_class_name = link_class
        current_attrs: dict[str, Any] = {}
        if isinstance(link, Mapping):
            href = str(link.get("href", "") or "").strip()
            label = str(link.get("label", "") or "").strip()
            label_html = str(link.get("label_html", "") or "")
            current_class_name = " ".join(
                part for part in (link_class, str(link.get("class_name", "") or "")) if part
            )
            attrs_candidate = link.get("attrs")
            if isinstance(attrs_candidate, Mapping):
                current_attrs = {
                    str(key): value for key, value in attrs_candidate.items() if str(key) not in {"class", "href"}
                }
        else:
            label, href = link
            label = str(label).strip()
            href = str(href).strip()
        if not href or (not label and not label_html):
            continue
        link_content = label_html or html.escape(label)
        rendered_links.append(
            f"<a"
            f"{_render_class_attr(current_class_name, q)}"
            f" href={q}{html.escape(href, quote=True)}{q}"
            f"{_render_attrs(current_attrs, q)}>{link_content}</a>"
        )
    if not rendered_links:
        return ""
    inner_html = separator.join(rendered_links)
    if not container_class and not container_attrs:
        return inner_html
    return (
        f"<{container_tag}"
        f"{_render_class_attr(container_class, q)}"
        f"{_render_attrs(container_attrs, q)}>"
        f"{inner_html}</{container_tag}>"
    )
