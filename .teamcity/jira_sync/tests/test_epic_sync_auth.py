import time
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from jira_sync import github_auth


@pytest.fixture
def app_credentials(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem)
    return key


@pytest.fixture
def token_request():
    with patch("jira_sync.github_auth.requests.post") as post:
        post.return_value = Mock(
            status_code=201, json=Mock(return_value={"token": "installation-token"})
        )
        yield post


def test_exchange_signs_jwt_and_scopes_token(app_credentials, token_request, capsys):
    now = int(time.time())
    with patch("jira_sync.github_auth.time.time", return_value=now):
        assert github_auth.get_installation_token() == "installation-token"

    token_request.assert_called_once()
    args, kwargs = token_request.call_args
    assert args == ("https://api.github.com/app/installations/456/access_tokens",)
    assertion = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(assertion, app_credentials.public_key(), algorithms=["RS256"])
    assert claims == {"iat": now - 60, "exp": now + 540, "iss": "123"}
    assert kwargs["json"] == {
        "repositories": ["repo"],
        "permissions": {"issues": "write"},
    }
    assert kwargs["timeout"] == 30
    assert kwargs["allow_redirects"] is False
    captured = capsys.readouterr()
    assert captured.out == "GitHub App authentication succeeded\n"
    assert captured.err == ""
