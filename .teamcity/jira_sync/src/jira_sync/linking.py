"""Shared helpers for encoding and parsing GitHub<->Jira links."""

from __future__ import annotations

import re
from copy import deepcopy

from jira_sync.jira_client import adf_to_text, text_to_adf

GH_URL_RE = re.compile(r"github\.com/[^/\s]+/[^/\s]+/(?:issues|pull)/(\d+)")
SYNC_SEPARATOR = "----------------------------------------"
SYNC_FOOTER_RE = re.compile(
    rf"(?m)^(?:{re.escape(SYNC_SEPARATOR)}[ \t]*\n)?Automatically synced at:\s*\S+$"
)


def sync_footer(url: str) -> str:
    return f"Automatically synced at: {url}"


def append_sync_footer(body: str, url: str) -> str:
    description = remove_sync_footer(body)
    if description:
        description = f"{description}\n\n{SYNC_SEPARATOR}\n"
    return f"{description}{sync_footer(url)}"


def build_jira_description(gh_url: str, body: str) -> str:
    return append_sync_footer(body, gh_url)


def _remove_inline_footer(paragraph: dict, text: str) -> None:
    """Remove matched lines by text offset, retaining untouched inline nodes."""
    spans = []
    for match in SYNC_FOOTER_RE.finditer(text):
        start, end = match.span()
        if start and text[start - 1] == "\n":
            start -= 1
        elif end < len(text) and text[end] == "\n":
            end += 1
        spans.append((start, end))
    if not spans:
        return
    _remove_inline_ranges(paragraph, spans)


def _remove_inline_ranges(paragraph: dict, spans: list[tuple[int, int]]) -> None:
    """Remove text ranges without rebuilding untouched inline nodes."""
    content = []
    offset = 0
    for inline in paragraph.get("content", []):
        value = adf_to_text({"content": [{"type": "paragraph", "content": [inline]}]})
        end = offset + len(value)
        cursor = offset
        for start, stop in spans:
            if stop <= cursor or start >= end:
                continue
            if start > cursor:
                content.append(
                    {**inline, "text": value[cursor - offset : start - offset]}
                )
            cursor = min(end, max(cursor, stop))
        if cursor == offset:
            content.append(inline)
        elif cursor < end:
            content.append({**inline, "text": value[cursor - offset :]})
        offset = end
    paragraph["content"] = content


def remove_adf_sync_footer(description: dict) -> dict:
    """Remove tracking ranges across paragraphs, preserving authored rich text."""
    document = deepcopy(description)
    nodes = document.get("content", [])
    content = []
    i = 0
    while i < len(nodes):
        node = nodes[i]
        text = adf_to_text({"content": [node]})

        if (
            node.get("type") == "paragraph"
            and i + 1 < len(nodes)
            and nodes[i + 1].get("type") == "paragraph"
        ):
            following = nodes[i + 1]
            next_text = adf_to_text({"content": [following]})
            boundary = len(text) + 1
            match = next(
                (
                    match
                    for match in SYNC_FOOTER_RE.finditer(f"{text}\n{next_text}")
                    if match.start() < boundary and match.end() > boundary
                ),
                None,
            )
            if match:
                start = match.start()
                end = match.end() - boundary
                if start and text[start - 1] == "\n":
                    start -= 1
                if end < len(next_text) and next_text[end] == "\n":
                    end += 1
                _remove_inline_ranges(node, [(start, len(text))])
                _remove_inline_ranges(following, [(0, end)])
                if (
                    not node["content"]
                    and content
                    and not text.strip().startswith(SYNC_SEPARATOR)
                    and (
                        content[-1].get("type") == "rule"
                        or adf_to_text({"content": [content[-1]]}).strip()
                        == SYNC_SEPARATOR
                    )
                ):
                    content.pop()
                content.extend(part for part in (node, following) if part["content"])
                i += 2
                continue

        if node.get("type") == "paragraph" and SYNC_FOOTER_RE.fullmatch(text.strip()):
            if (
                content
                and not text.strip().startswith(SYNC_SEPARATOR)
                and (
                    content[-1].get("type") == "rule"
                    or adf_to_text({"content": [content[-1]]}).strip() == SYNC_SEPARATOR
                )
            ):
                content.pop()
            i += 1
            continue

        if node.get("type") == "paragraph":
            _remove_inline_footer(node, text)
        content.append(node)
        i += 1

    document["content"] = content
    return document


def build_jira_adf_description(url: str, description: dict) -> dict:
    """Replace tracking blocks or inline footer lines, preserving authored rich text."""
    document = remove_adf_sync_footer(description)
    content = document["content"]
    footer = sync_footer(url)
    if content:
        footer = f"{SYNC_SEPARATOR}\n{footer}"
    document["content"] = content + text_to_adf(footer)["content"]
    return document


def ensure_jira_description_postfix(
    current_description: str, gh_url: str
) -> str | None:
    """Append a sync footer, preserving the Jira-authored description."""
    updated_description = build_jira_description(
        gh_url, remove_sync_footer(current_description)
    )
    if current_description == updated_description:
        return None
    return updated_description


def remove_sync_footer(description: str) -> str:
    """Remove a sync footer while preserving authored text."""
    return SYNC_FOOTER_RE.sub("", description).strip()


def parse_gh_number(description: str | None) -> int | None:
    """Extract GitHub issue/PR number from description.

    Prefers the tracking footer URL when present, falling back to other
    URLs (authored smart-cards) only if no footer is found. This prevents
    accidentally selecting an unrelated issue linked in the description.
    """
    if not description:
        return None

    # First, try to find a URL in the tracking footer
    # The footer is typically at the end, possibly with separator before it
    footer_match = SYNC_FOOTER_RE.search(description)
    if footer_match:
        footer_text = footer_match.group(0)
        url_match = GH_URL_RE.search(footer_text)
        if url_match:
            return int(url_match.group(1))

    # Fallback: search for any GitHub URL in the description
    # This handles descriptions without a footer
    match = GH_URL_RE.search(description)
    return int(match.group(1)) if match else None
