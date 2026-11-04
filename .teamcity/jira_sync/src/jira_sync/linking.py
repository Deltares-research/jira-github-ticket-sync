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


def build_jira_adf_description(url: str, description: dict) -> dict:
    """Replace tracking-footer blocks without rebuilding Jira-authored rich text."""
    document = deepcopy(description)
    content = []
    for node in document.get("content", []):
        text = adf_to_text({"content": [node]})
        if node.get("type") == "paragraph" and SYNC_FOOTER_RE.fullmatch(text.strip()):
            if content and (
                content[-1].get("type") == "rule"
                or adf_to_text({"content": [content[-1]]}).strip() == SYNC_SEPARATOR
            ):
                content.pop()
            continue
        content.append(node)
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
    match = GH_URL_RE.search(description or "")
    return int(match.group(1)) if match else None
