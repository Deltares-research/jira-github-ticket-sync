"""Authenticate and run Jira-to-GitHub epic synchronization.

Requires GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, GITHUB_APP_PRIVATE_KEY
(multiline PEM), and GITHUB_REPOSITORY. The generated GITHUB_TOKEN stays in
this process; it is never printed or written to disk. Runs must finish before
the installation token expires; automatic refresh is not provided.
Alternatively, supply GITHUB_TOKEN without any GitHub App variables.
"""

from __future__ import annotations

import os
import time

import jwt
import requests

from jira_sync import jira_client, jira_to_github
from jira_sync.github_client import API_BASE

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


def installation_token() -> str:
    app_id = _required_env("GITHUB_APP_ID")
    installation_id = _required_env("GITHUB_APP_INSTALLATION_ID")
    private_key = _required_env("GITHUB_APP_PRIVATE_KEY")
    repository = _required_env("GITHUB_REPOSITORY")
    for name, value in (
        ("GITHUB_APP_ID", app_id),
        ("GITHUB_APP_INSTALLATION_ID", installation_id),
    ):
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"{name} must be a positive integer")
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("GITHUB_REPOSITORY must have the form owner/repo")

    now = int(time.time())
    try:
        assertion = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": app_id},
            private_key,
            algorithm="RS256",
        )
    except (ValueError, TypeError, jwt.PyJWTError):
        raise ValueError(
            "GITHUB_APP_PRIVATE_KEY must be a valid RSA PEM private key"
        ) from None

    try:
        response = requests.post(
            f"{API_BASE}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {assertion}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "repositories": [parts[1]],
                "permissions": {"issues": "write"},
            },
            timeout=30,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("GitHub App token exchange failed: network error") from None
    if response.status_code != 201:
        raise RuntimeError(
            f"GitHub App token exchange failed: HTTP {response.status_code}. "
            "Check the app installation, repository access, and Issues permission."
        )
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        raise RuntimeError("GitHub App token exchange returned invalid JSON") from None
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("GitHub App token exchange returned no valid token")
    print("GitHub App authentication succeeded")
    return token


def main() -> None:
    if any(name in os.environ for name in APP_ENV_VARS):
        os.environ["GITHUB_TOKEN"] = installation_token()
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
