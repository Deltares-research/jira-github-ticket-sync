from copy import deepcopy

import pytest
from jira_sync.jira_client import adf_to_text, text_to_adf
from jira_sync.linking import (
    SYNC_SEPARATOR,
    append_sync_footer,
    build_jira_adf_description,
    build_jira_description,
    ensure_jira_description_postfix,
    parse_gh_number,
    remove_adf_sync_footer,
    remove_sync_footer,
    sync_footer,
)


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("marked_run", [False, True])
@pytest.mark.parametrize("separator", ["", SYNC_SEPARATOR + "\n"])
def test_footer_replacement_preserves_authored_content(split, marked_run, separator):
    before, after = "Before", "After"
    label = separator + "Automatically synced at:"
    url = "https://github.com/o/r/issues/9"
    document = text_to_adf(
        f"{before}\n{label}" + ("\n\n" if split else "\n") + f"{url}\n{after}"
    )
    for paragraph in document["content"]:
        if marked_run:
            paragraph["content"] = [
                {"type": "text", "text": adf_to_text({"content": [paragraph]})}
            ]
        else:
            runs = []
            for inline in paragraph["content"]:
                for index, line in enumerate(inline["text"].split("\n")):
                    if index:
                        runs.append({"type": "hardBreak"})
                    if line:
                        runs.append({**inline, "text": line})
            paragraph["content"] = runs
        for inline in paragraph["content"]:
            if inline["type"] == "text":
                inline["marks"] = [{"type": "strong"}]
    original = deepcopy(document)
    cleaned = remove_adf_sync_footer(document)
    assert adf_to_text(cleaned) == (
        f"{before}\n\n{after}" if split else f"{before}\n{after}"
    )
    assert all(
        node["marks"] == [{"type": "strong"}]
        for paragraph in cleaned["content"]
        for node in paragraph["content"]
        if node["type"] == "text"
    )
    updated = build_jira_adf_description("https://github.com/o/r/issues/11", document)
    assert updated["content"][:-1] == cleaned["content"]
    assert "issues/9" not in adf_to_text(updated)
    assert parse_gh_number(adf_to_text(updated)) == 11
    assert (
        build_jira_adf_description("https://github.com/o/r/issues/11", updated)
        == updated
    )
    assert document == original


@pytest.mark.parametrize("separator", ["", SYNC_SEPARATOR, "rule"])
def test_exclusive_footer_blocks_are_removed(separator):
    document = text_to_adf(
        "Automatically synced at:\n\nhttps://github.com/o/r/issues/9"
    )
    if separator:
        document["content"][:0] = (
            [{"type": "rule"}]
            if separator == "rule"
            else text_to_adf(separator)["content"]
        )
    assert remove_adf_sync_footer(document)["content"] == []


def test_tracking_footer_takes_precedence_over_authored_links():
    authored = "https://github.com/o/r/issues/42"
    assert (
        parse_gh_number(
            authored + "\n\nAutomatically synced at:\n\nhttps://github.com/o/r/pull/5"
        )
        == 5
    )
    assert parse_gh_number(authored) == 42


def test_sync_footer_format():
    # Arrange
    issue_url = "https://github.com/owner/repo/issues/1"

    # Act
    footer = sync_footer(issue_url)

    # Assert
    assert footer == "Automatically synced at: https://github.com/owner/repo/issues/1"


def test_append_sync_footer_adds_separator_after_description():
    # Arrange
    description = "description"
    issue_url = "https://example.test/issue/1"

    # Act
    result = append_sync_footer(description, issue_url)

    # Assert
    assert result == (
        f"description\n\n{SYNC_SEPARATOR}\n"
        "Automatically synced at: https://example.test/issue/1"
    )


def test_build_jira_description_uses_tracked_link_as_postfix():
    # Arrange
    issue_url = "https://github.com/owner/repo/issues/1"

    # Act
    description = build_jira_description(issue_url, "")

    # Assert
    assert (
        description == "Automatically synced at: https://github.com/owner/repo/issues/1"
    )


def test_build_jira_description_appends_tracking_link_after_body():
    # Arrange
    issue_url = "https://github.com/owner/repo/issues/1"
    original_description = "original issue text"

    # Act
    description = build_jira_description(issue_url, original_description)

    # Assert
    assert description == (
        "original issue text\n\n"
        f"{SYNC_SEPARATOR}\nAutomatically synced at: https://github.com/owner/repo/issues/1"
    )


def test_ensure_jira_description_postfix_appends_when_missing():
    # Arrange
    description = "human-written summary"
    issue_url = "https://github.com/owner/repo/issues/1"

    # Act
    result = ensure_jira_description_postfix(description, issue_url)

    # Assert
    assert result == (
        "human-written summary\n\n"
        f"{SYNC_SEPARATOR}\nAutomatically synced at: https://github.com/owner/repo/issues/1"
    )


def test_ensure_jira_description_postfix_handles_empty_description():
    # Arrange
    description = ""
    issue_url = "https://github.com/owner/repo/issues/1"

    # Act
    result = ensure_jira_description_postfix(description, issue_url)

    # Assert
    assert result == "Automatically synced at: https://github.com/owner/repo/issues/1"


def test_ensure_jira_description_postfix_replaces_existing_footer():
    # Arrange
    current = (
        "Automatically synced at: https://github.com/owner/repo/issues/99\n\nsummary"
    )
    issue_url = "https://github.com/owner/repo/issues/1"

    # Act
    result = ensure_jira_description_postfix(current, issue_url)

    # Assert
    assert result == (
        f"summary\n\n{SYNC_SEPARATOR}\n"
        "Automatically synced at: https://github.com/owner/repo/issues/1"
    )


def test_remove_sync_footer_preserves_content():
    # Arrange
    description = (
        "Automatically synced at: https://github.com/owner/repo/issues/1\n\nsummary"
    )

    # Act
    result = remove_sync_footer(description)

    # Assert
    assert result == "summary"


def test_parse_gh_number_extracts_issue_number():
    # Arrange
    description = "Automatically synced at: https://github.com/owner/repo/issues/42"

    # Act
    number = parse_gh_number(description)

    # Assert
    assert number == 42


def test_parse_gh_number_extracts_pull_number():
    # Arrange
    description = "Automatically synced at: https://github.com/owner/repo/pull/7"

    # Act
    number = parse_gh_number(description)

    # Assert
    assert number == 7


def test_parse_gh_number_returns_none_without_url():
    # Arrange
    description = "plain summary"

    # Act
    number = parse_gh_number(description)

    # Assert
    assert number is None


def test_parse_gh_number_handles_none():
    # Arrange
    description = None

    # Act
    number = parse_gh_number(description)

    # Assert
    assert number is None
