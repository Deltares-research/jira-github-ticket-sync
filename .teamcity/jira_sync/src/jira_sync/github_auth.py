"""GitHub App authentication to generate installation access tokens.

Requires GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, GITHUB_APP_PRIVATE_KEY
(multiline PEM), and GITHUB_REPOSITORY. The generated token stays in the
process; it is never printed or written to disk.
"""

from __future__ import annotations

import os
import time

import jwt
import requests

from jira_sync.github_client import API_BASE


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set and non-empty")
    return value


def get_installation_token() -> str:
    """Generate a GitHub App installation access token.

    Exchanges a GitHub App private key for a repository-scoped access token.
    Validates all required environment variables and handles errors gracefully.

    Returns:
        A valid GitHub API access token string.

    Raises:
        ValueError: If any required environment variable is missing or invalid.
        RuntimeError: If the token exchange fails.
    """
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
