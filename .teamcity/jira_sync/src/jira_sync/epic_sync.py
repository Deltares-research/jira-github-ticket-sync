"""Run Jira-to-GitHub epic synchronization.

Orchestrates the sync process. For GitHub authentication, see github_auth.py.

The GITHUB_TOKEN is set either:
- From GITHUB_TOKEN environment variable directly, OR
- Generated from GitHub App credentials via github_auth.get_installation_token()

Runs must finish before the installation token expires; automatic refresh is
not provided.
"""

from __future__ import annotations

import os

from jira_sync import jira_client, jira_to_github
from jira_sync.github_auth import get_installation_token

APP_ENV_VARS = (
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY",
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set and non-empty")
    return value


def main() -> None:
    if any(name in os.environ for name in APP_ENV_VARS):
        os.environ["GITHUB_TOKEN"] = get_installation_token()
    else:
        _required_env("GITHUB_TOKEN")
    epic_key = os.environ["JIRA_EPIC_KEY"]
    if jira_client.get_issue(epic_key) is None:
        raise RuntimeError(
            f"Cannot access Jira epic {epic_key} at {os.environ['JIRA_BASE_URL']} "
            f"using JIRA_EMAIL={os.environ['JIRA_EMAIL']}. "
            "Check the CI Jira site, token owner, token scopes, Browse Projects "
            "permission, and issue security. Sync aborted before making changes."
        )
    jira_to_github.sync_all()


if __name__ == "__main__":
    main()
