from copy import deepcopy

import pytest
from jira_sync.jira_client import adf_to_text
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


@pytest.mark.parametrize("separator", [False, True])
@pytest.mark.parametrize("trailing_text", [False, True])
@pytest.mark.parametrize("break_type", ["hardBreak", "newline"])
def test_replace_footer_inside_paragraph_preserves_inline_nodes(
    separator, trailing_text, break_type
):
    authored = {"type": "text", "text": "Authored text", "marks": [{"type": "strong"}]}
    following = {
        "type": "text",
        "text": "More text",
        "marks": [{"type": "link", "attrs": {"href": "https://example.test"}}],
    }
    inline = [authored]
    lines = ([SYNC_SEPARATOR] if separator else []) + [
        "Automatically synced at: ",
        "https://github.com/owner/repo/issues/9",
    ]
    for index, text in enumerate(lines):
        if index != len(lines) - 1:
            inline.append(
                {"type": "hardBreak"}
                if break_type == "hardBreak"
                else {"type": "text", "text": "\n"}
            )
        inline.append({"type": "text", "text": text})
    if trailing_text:
        inline.extend([{"type": "hardBreak"}, following])
    document = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": inline}],
    }
    original = deepcopy(document)
    url = "https://github.com/owner/repo/issues/11"

    updated = build_jira_adf_description(url, document)

    expected = [authored] + (
        [{"type": "hardBreak"}, following] if trailing_text else []
    )
    assert updated["content"][0]["content"] == expected
    assert parse_gh_number(adf_to_text(updated)) == 11
    assert "issues/9" not in adf_to_text(updated)
    assert build_jira_adf_description(url, updated) == updated
    assert document == original


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Before\nAutomatically synced at: https://github.com/o/r/issues/9",
            ["Before"],
        ),
        ("Automatically synced at: https://github.com/o/r/issues/9\nAfter", ["After"]),
        (
            "Before\nAutomatically synced at: https://github.com/o/r/issues/9\nAfter",
            ["Before", "\nAfter"],
        ),
    ],
)
def test_replace_footer_within_marked_text_node(text, expected):
    marks = [{"type": "strong"}]
    document = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text, "marks": marks}],
            }
        ],
    }

    updated = build_jira_adf_description("https://github.com/o/r/issues/11", document)

    assert updated["content"][0]["content"] == [
        {"type": "text", "text": value, "marks": marks} for value in expected
    ]


@pytest.mark.parametrize("before", [False, True])
@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("separator", ["none", "paragraph", "rule", "inline"])
@pytest.mark.parametrize("break_type", ["hardBreak", "newline"])
def test_split_footer_preserves_authored_inline_nodes(
    before, after, separator, break_type
):
    authored = {"type": "text", "text": "Authored", "marks": [{"type": "strong"}]}
    notes = {
        "type": "text",
        "text": "Notes",
        "marks": [{"type": "link", "attrs": {"href": "https://example.test"}}],
    }
    br = (
        {"type": "hardBreak"}
        if break_type == "hardBreak"
        else {"type": "text", "text": "\n"}
    )
    label = (
        ([authored, br] if before else [])
        + (
            [{"type": "text", "text": SYNC_SEPARATOR}, br]
            if separator == "inline"
            else []
        )
        + [{"type": "text", "text": "Automatically synced at:"}]
    )
    url = [{"type": "text", "text": "https://github.com/o/r/issues/9"}] + (
        [br, notes] if after else []
    )
    prefix = []
    if separator == "paragraph":
        prefix = [
            {"type": "paragraph", "content": [{"type": "text", "text": SYNC_SEPARATOR}]}
        ]
    elif separator == "rule":
        prefix = [{"type": "rule"}]
    document = {
        "type": "doc",
        "version": 1,
        "content": prefix
        + [
            {"type": "paragraph", "content": label},
            {"type": "paragraph", "content": url},
        ],
    }
    original = deepcopy(document)
    expected = (
        (prefix if before else [])
        + ([{"type": "paragraph", "content": [authored]}] if before else [])
        + ([{"type": "paragraph", "content": [notes]}] if after else [])
    )

    cleaned = remove_adf_sync_footer(document)
    updated = build_jira_adf_description("https://github.com/o/r/issues/11", document)

    assert cleaned["content"] == expected
    assert updated["content"][: len(expected)] == expected
    assert "issues/9" not in adf_to_text(updated)
    assert parse_gh_number(adf_to_text(updated)) == 11
    assert (
        build_jira_adf_description("https://github.com/o/r/issues/11", updated)
        == updated
    )
    assert document == original


def test_split_footer_preserves_partial_marked_text_and_other_nodes():
    marks = [{"type": "strong"}]
    card = {"type": "inlineCard", "attrs": {"url": "https://example.test/notes"}}
    heading = {
        "type": "heading",
        "attrs": {"level": 2},
        "content": [{"type": "text", "text": "Heading"}],
    }
    document = {
        "type": "doc",
        "version": 1,
        "content": [
            heading,
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Before\nAutomatically synced at:",
                        "marks": marks,
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "https://github.com/o/r/issues/9\nAfter",
                        "marks": marks,
                    },
                    card,
                ],
            },
        ],
    }
    original = deepcopy(document)

    cleaned = remove_adf_sync_footer(document)

    assert cleaned["content"] == [
        heading,
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Before", "marks": marks}],
        },
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "After", "marks": marks}, card],
        },
    ]
    assert document == original


@pytest.mark.parametrize(
    ("label", "url"),
    [
        ("Notes about Automatically synced at:", "https://github.com/o/r/issues/9"),
        ("Automatically synced at:", "See https://github.com/o/r/issues/9 for context"),
    ],
)
def test_split_footer_does_not_remove_authored_prose(label, url):
    document = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            for text in (label, url)
        ],
    }

    assert remove_adf_sync_footer(document) == document


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


def test_replace_footer_spanning_adjacent_paragraphs():
    """Test removing footers where label and URL are in separate paragraphs."""
    # Arrange: footer split across two paragraphs
    authored = {"type": "text", "text": "Authored text"}
    document = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [authored]},
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Automatically synced at:"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "https://github.com/owner/repo/issues/9"}
                ],
            },
        ],
    }
    original = deepcopy(document)
    url = "https://github.com/owner/repo/issues/11"

    # Act
    updated = build_jira_adf_description(url, document)

    # Assert: old footer paragraphs removed, new footer added
    assert parse_gh_number(adf_to_text(updated)) == 11
    assert "issues/9" not in adf_to_text(updated)
    # Authored text preserved
    assert "Authored text" in adf_to_text(updated)
    # Idempotent
    assert build_jira_adf_description(url, updated) == updated
    # Original not mutated
    assert document == original


def test_replace_footer_spanning_adjacent_paragraphs_with_separator():
    """Test removing footers with separator line before label paragraph."""
    # Arrange: footer with separator, split across paragraphs
    authored = {"type": "text", "text": "Authored text"}
    document = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [authored]},
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": SYNC_SEPARATOR}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Automatically synced at:"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "https://github.com/owner/repo/issues/9"}
                ],
            },
        ],
    }
    original = deepcopy(document)
    url = "https://github.com/owner/repo/issues/11"

    # Act
    updated = build_jira_adf_description(url, document)

    # Assert: separator and old footer paragraphs removed
    assert parse_gh_number(adf_to_text(updated)) == 11
    assert "issues/9" not in adf_to_text(updated)
    assert "Authored text" in adf_to_text(updated)
    assert build_jira_adf_description(url, updated) == updated
    assert document == original
