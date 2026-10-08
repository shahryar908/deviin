import secrets

import pytest
from fastapi.testclient import TestClient

import github_service
import settings
import store


def test_token_roundtrip():
    settings.GITHUB_TOKEN_ENCRYPTION_KEY = settings.GITHUB_TOKEN_ENCRYPTION_KEY or _fallback_key()
    enc = github_service.encrypt_token("gho_secret")
    assert github_service.decrypt_token(enc) == "gho_secret"


def _fallback_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def test_state_jwt_roundtrip():
    settings.GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET or secrets.token_urlsafe(16)
    s = github_service.make_state("u-123")
    assert github_service.verify_state(s) == "u-123"


def test_callback_exchange_and_user(monkeypatch):
    async def fake_exchange(code):
        return {"access_token": "gho_secret", "scope": "repo read:user"}

    async def fake_user(token):
        return {"id": 42, "login": "ghuser"}

    settings.GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET or secrets.token_urlsafe(16)
    settings.GITHUB_TOKEN_ENCRYPTION_KEY = settings.GITHUB_TOKEN_ENCRYPTION_KEY or _fallback_key()

    monkeypatch.setattr(github_service, "exchange_code", fake_exchange)
    monkeypatch.setattr(github_service, "fetch_user", fake_user)

    state = github_service.make_state("local")
    import asyncio
    out = asyncio.run(github_service.do_callback("code123", state))
    assert out["login"] == "ghuser"
    row = store.get_github_connection("local")
    assert row is not None
    assert store.delete_github_connection("local") is True


def test_commit_endpoint(monkeypatch):
    async def fake_upsert(*args, **kwargs):
        return {"sha": "abc123"}

    settings.GITHUB_TOKEN_ENCRYPTION_KEY = settings.GITHUB_TOKEN_ENCRYPTION_KEY or _fallback_key()
    monkeypatch.setattr(github_service, "upsert_file", fake_upsert)

    # Patch store so get_token can find an encrypted token without a real DB row.
    monkeypatch.setattr(
        store,
        "get_github_connection",
        lambda uid: {"encrypted_access_token": github_service.encrypt_token("t")},
    )

    # Also patch sandbox health of TestClient needing server import.
    import server

    client = TestClient(server.app)
    r = client.post(
        "/github/repos/o/r/commit",
        json={"path": "a.md", "content": "hi", "message": "msg", "branch": "main"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sha"] == "abc123"
