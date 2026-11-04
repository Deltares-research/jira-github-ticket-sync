"""Shared pytest fixtures for the jira_sync package tests."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Override inherited configuration before application modules are imported.
os.environ["JIRA_EPIC_KEY"] = "MLPS-118"


@pytest.fixture
def formatted_description():
    def paragraph(text, **extra):
        return {
            "type": "paragraph",
            "content": [{"type": "text", "text": text, **extra}],
        }

    return {
        "type": "doc",
        "version": 1,
        "content": [
            paragraph("Goal", marks=[{"type": "strong"}]),
            paragraph("Publish the Python package on Nexus."),
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [paragraph(title)],
                    }
                    for title in [
                        "Nexus Python workshop",
                        "How to: install Python proxy",
                    ]
                ],
            },
            {"type": "rule"},
            paragraph(
                "Workshop",
                marks=[
                    {"type": "link", "attrs": {"href": "https://example.test/workshop"}}
                ],
            ),
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "inlineCard",
                        "attrs": {
                            "url": "https://example.test/publish?title=Full+title&pageId=123"
                        },
                    }
                ],
            },
        ],
    }


@pytest.fixture
def formatted_markdown():
    return (
        "**Goal**\n\n"
        "Publish the Python package on Nexus.\n\n"
        "- Nexus Python workshop\n- How to: install Python proxy\n\n"
        "---\n\n[Workshop](<https://example.test/workshop>)\n\n"
        "https://example.test/publish?title=Full+title&pageId=123"
    )


@pytest.fixture(autouse=True)
def required_env(monkeypatch):
    """Provide dummy credentials so modules can be imported/used in isolation."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "dummy-token")
    monkeypatch.setenv("JIRA_EPIC_KEY", "MLPS-118")
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-gh-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
