"""Jira-to-GitHub reconciliation helpers.

Each full sync finds every Jira issue under the tracked epic and mirrors it
onto GitHub: issues not yet linked to a GitHub issue/PR get a new
GitHub issue created, with a sync footer on GitHub recording the Jira link;
already-linked issues have their description kept in sync with the
Jira summary/description, their comments mirrored, and their Jira status
mirrored back onto GitHub (open <-> closed).

Bold text, bullets, links and rules use Markdown in GitHub descriptions and comments.
Jira is read-only: descriptions, comments and other Jira data are never modified.
GitHub tracking footers identify existing mirrors; legacy Jira links remain readable.
Multiple mirrors for the same Jira issue abort sync rather than selecting arbitrarily.
Tracking content is removed from an ADF copy before rendering mirrored descriptions.

Required env vars: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_EPIC_KEY, GITHUB_TOKEN,
GITHUB_REPOSITORY.
"""

from __future__ import annotations

import os
import re

import jira_sync.github_client as gh
import jira_sync.jira_client as jira
from jira_sync.linking import (
    append_sync_footer,
    parse_gh_number,
    remove_adf_sync_footer,
    remove_sync_footer,
    sync_footer,
)

JIRA_EPIC_KEY = os.environ["JIRA_EPIC_KEY"]
JIRA_JQL = f'parent = "{JIRA_EPIC_KEY}"'

JIRA_COMMENT_ID_RE = re.compile(r"<!-- jira-comment-id:(\S+) -->")
JIRA_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*-\d+")

# Retain the legacy GitHub-to-Jira marker to avoid re-mirroring old comments.
JIRA_TO_GH_COMMENT_PREFIX = "_Synced from Jira comment"
GH_TO_JIRA_COMMENT_PREFIX = "Synced from GitHub comment"


def build_synced_body(key: str, description: str) -> str:
    jira_url = f"{os.environ['JIRA_BASE_URL'].rstrip('/')}/browse/{key}"
    return append_sync_footer(description, jira_url)


def create_and_link_gh_issue(summary: str, body: str) -> int | None:
    return gh.create_issue(title=summary, body=body)


def build_epic_body(description: str) -> str:
    jira_url = f"{os.environ['JIRA_BASE_URL'].rstrip('/')}/browse/{JIRA_EPIC_KEY}"
    return append_sync_footer(description, jira_url)


def find_github_issue(key: str) -> dict | None:
    jira_url = f"{os.environ['JIRA_BASE_URL'].rstrip('/')}/browse/{key}"
    footer = sync_footer(jira_url)
    repo = os.environ["GITHUB_REPOSITORY"]
    matches = [
        item
        for item in gh.search_issues(f'repo:{repo} "{key}" in:body')
        if (item.get("body") or "").rstrip().endswith(footer)
    ]
    if len(matches) > 1:
        numbers = ", ".join(f"#{item['number']}" for item in matches)
        raise RuntimeError(
            f"{key}: multiple GitHub mirrors in {repo}: {numbers}. "
            "Remove the tracking footer from duplicate issues before syncing."
        )
    return matches[0] if matches else None


def ensure_epic_issue() -> dict | None:
    epic = jira.get_issue(JIRA_EPIC_KEY)
    if epic is None:
        print(f"{JIRA_EPIC_KEY}: Jira epic not found, skipping GitHub parent sync")
        return None

    summary = epic["fields"]["summary"]
    original = epic["fields"].get("description")
    description = jira.adf_to_text(
        remove_adf_sync_footer(original)
        if isinstance(original, dict)
        else remove_sync_footer(original or ""),
        markdown=True,
    )
    expected_body = build_epic_body(description)
    item = find_github_issue(JIRA_EPIC_KEY)
    if item is not None:
        if item.get("title") != summary or item.get("body") != expected_body:
            gh.update_issue(item["number"], title=summary, body=expected_body)
        return gh.get_issue(item["number"]) or item

    number = gh.create_issue(summary, expected_body)
    if number is None:
        print(f"{JIRA_EPIC_KEY}: failed to create GitHub parent issue")
        return None
    print(f"{JIRA_EPIC_KEY}: created GitHub parent #{number}")
    return gh.get_issue(number)


def link_to_epic(parent_issue: dict | None, child_issue: dict) -> None:
    if parent_issue is None or parent_issue["number"] == child_issue["number"]:
        return
    child_id = child_issue.get("id")
    if child_id is None:
        print(
            f"#{child_issue['number']}: missing GitHub issue id, skipping parent link"
        )
        return
    parent_number = parent_issue["number"]
    if child_id not in gh.list_sub_issue_ids(parent_number):
        gh.add_sub_issue(parent_number, child_id)


def sync_comments(key: str, number: int) -> None:
    already_mirrored: set[str] = set()
    for gh_comment in gh.list_comments(number):
        match = JIRA_COMMENT_ID_RE.search(gh_comment.get("body", ""))
        if match:
            already_mirrored.add(match.group(1))

    for comment in jira.list_comments(key):
        comment_id = comment["id"]
        if comment_id in already_mirrored:
            continue
        original = comment.get("body")
        if jira.adf_to_text(original).startswith(GH_TO_JIRA_COMMENT_PREFIX):
            # This comment originated on GitHub; no need to mirror it back.
            continue
        text = jira.adf_to_text(original, markdown=True)
        author = comment.get("author", {}).get("displayName", "Jira user")
        body = (
            f"{JIRA_TO_GH_COMMENT_PREFIX} by {author}:_\n\n{text}\n\n"
            f"<!-- jira-comment-id:{comment_id} -->"
        )
        gh.add_comment(number, body)
        print(f"{key}: mirrored Jira comment {comment_id} to GitHub #{number}")


def delete_missing_jira_issues(
    parent_issue: dict | None, jira_issue_keys: set[str]
) -> None:
    if parent_issue is None:
        return

    footer_prefix = (
        f"Automatically synced at: {os.environ['JIRA_BASE_URL'].rstrip('/')}/browse/"
    )
    for gh_item in gh.list_sub_issues(parent_issue["number"]):
        body_lines = (gh_item.get("body") or "").splitlines()
        footer = body_lines[-1] if body_lines else ""
        if not footer.startswith(footer_prefix):
            continue

        jira_key = footer[len(footer_prefix) :]
        if not JIRA_KEY_RE.fullmatch(jira_key) or jira_key in jira_issue_keys:
            continue
        if not jira.issue_is_missing(jira_key):
            continue

        node_id = gh_item.get("node_id")
        if node_id is not None and gh.delete_issue(node_id):
            print(
                f"Deleted GitHub #{gh_item['number']}: Jira issue {jira_key} is missing"
            )


def ensure_github_issue(
    issue: dict,
) -> tuple[int | None, dict | None, str]:
    key = issue["key"]
    original = issue["fields"].get("description")
    plain_description = jira.adf_to_text(original)
    description = jira.adf_to_text(
        remove_adf_sync_footer(original)
        if isinstance(original, dict)
        else remove_sync_footer(original or ""),
        markdown=True,
    )
    gh_item = find_github_issue(key)
    number = (
        gh_item["number"] if gh_item is not None else parse_gh_number(plain_description)
    )
    if number is not None:
        gh_item = gh.get_issue(number)

    if number is not None and gh_item is None:
        print(f"{key}: linked GitHub #{number} not found, recreating")
        number = None

    expected_body = build_synced_body(key, description)
    if number is None:
        number = create_and_link_gh_issue(issue["fields"]["summary"], expected_body)
        if number is None:
            print(f"{key}: failed to create a linked GitHub issue, skipping")
            return None, None, expected_body

        print(f"{key}: created and linked GitHub #{number}")

    if gh_item is None:
        gh_item = gh.get_issue(number)
    return number, gh_item, expected_body


def sync_github_issue(
    issue: dict,
    parent_issue: dict | None,
    number: int,
    gh_item: dict,
    expected_body: str,
) -> None:
    key = issue["key"]
    link_to_epic(parent_issue, gh_item)

    if gh_item.get("body") != expected_body:
        gh.update_issue(number, body=expected_body)
        print(f"{key}: updated GitHub #{number} description from Jira")

    sync_comments(key, number)
    sync_issue_state(issue, number, gh_item)


def sync_issue_state(issue: dict, number: int, gh_item: dict) -> None:
    key = issue["key"]
    status_category = issue["fields"]["status"]["statusCategory"]["key"]
    jira_done = status_category == "done"
    gh_open = gh_item["state"] == "open"

    if jira_done and gh_open:
        gh.add_comment(number, f"Closing automatically: {key} was marked Done in Jira.")
        gh.set_state(number, "closed")
        print(f"Closed #{number} ({key} is Done)")
    elif not jira_done and not gh_open:
        gh.add_comment(
            number, f"Reopening automatically: {key} is no longer Done in Jira."
        )
        gh.set_state(number, "open")
        print(f"Reopened #{number} ({key} is not Done)")
    else:
        print(
            f"{key}: #{number} already in sync (jira_done={jira_done}, gh_open={gh_open})"
        )


def sync_jira_issue(issue: dict, parent_issue: dict | None) -> None:
    number, gh_item, expected_body = ensure_github_issue(issue)
    if number is None:
        return
    if gh_item is None:
        print(f"{issue['key']}: linked GitHub #{number} not found, skipping")
        return

    sync_github_issue(issue, parent_issue, number, gh_item, expected_body)


def sync_all() -> None:
    issues = jira.search(JIRA_JQL, fields=["status", "summary", "description"])
    print(f"Found {len(issues)} Jira issue(s) under {JIRA_EPIC_KEY}")
    parent_issue = ensure_epic_issue()

    for issue in issues:
        sync_jira_issue(issue, parent_issue)

    delete_missing_jira_issues(parent_issue, {issue["key"] for issue in issues})
