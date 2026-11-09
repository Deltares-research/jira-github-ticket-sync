"""Helpers for GitHub tracking footers and reading legacy Jira links."""

from __future__ import annotations

import re
from copy import deepcopy

from jira_sync.jira_client import adf_to_text

GH_URL_RE = re.compile(r"github\.com/[^/\s]+/[^/\s]+/(?:issues|pull)/(\d+)")
SYNC_SEPARATOR = "----------------------------------------"
SYNC_NOTICE = (
    "This issue is a read-only mirror of Jira. Please make edits in Jira; "
    "changes made here may be overwritten."
)
SYNC_FOOTER_RE = re.compile(
    rf"(?m)^(?:{re.escape(SYNC_SEPARATOR)}[ \t]*\n)?"
    rf"(?:{re.escape(SYNC_NOTICE)}\n\n)?Automatically synced at:\s*\S+$"
)


def sync_footer(url: str) -> str:
    return f"Automatically synced at: {url}"


def append_sync_footer(body: str, url: str) -> str:
    """Append editing guidance and a tracking link to a GitHub mirror."""
    description = remove_sync_footer(body)
    if description:
        description = f"{description}\n\n{SYNC_SEPARATOR}\n"
    return f"{description}{SYNC_NOTICE}\n\n{sync_footer(url)}"


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


def remove_sync_footer(description: str) -> str:
    """Remove a sync footer while preserving authored text."""
    return SYNC_FOOTER_RE.sub("", description).strip()


def parse_gh_number(description: str | None) -> int | None:
    """Prefer the tracking footer to unrelated authored GitHub links."""
    text = description or ""
    footer = SYNC_FOOTER_RE.search(text)
    match = GH_URL_RE.search(footer.group(0)) if footer else None
    if match is None:
        match = GH_URL_RE.search(text)
    return int(match.group(1)) if match else None
