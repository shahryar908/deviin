"""GitHub OAuth + repo management endpoints (HTTP via httpx, tokens Fernet-encrypted)."""

import secrets
import time
from typing import Any

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

import settings
import store

GITHUB_API = "https://api.github.com"
GITHUB_OAUTH = "https://github.com/login/oauth"


def _fernet() -> Fernet:
    key = settings.GITHUB_TOKEN_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("GITHUB_TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken as e:
        raise HTTPException(status_code=500, detail="token decrypt failed") from e


def make_state(user_id: str) -> str:
    return jwt.encode(
        {"user_id": user_id, "iat": int(time.time()), "exp": int(time.time()) + 600},
        settings.GITHUB_CLIENT_SECRET or secrets.token_urlsafe(8),
        algorithm="HS256",
    )


def verify_state(state: str) -> str:
    try:
        data = jwt.decode(state, settings.GITHUB_CLIENT_SECRET or "", algorithms=["HS256"])
        return data["user_id"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid state: {e}") from e


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


async def exchange_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GITHUB_OAUTH}/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_user(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GITHUB_API}/user", headers=_headers(token))
        r.raise_for_status()
        return r.json()


def auth_url(user_id: str) -> str:
    state = make_state(user_id)
    return (
        f"https://github.com/login/oauth/authorize?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}&scope=repo%20read:user&state={state}"
    )


async def do_callback(code: str, state: str) -> dict[str, Any]:
    store.init_db()
    user_id = verify_state(state)
    token_resp = await exchange_code(code)
    token = token_resp.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail=f"token exchange failed: {token_resp.get('error_description')}")
    user = await fetch_user(token)
    scopes = token_resp.get("scope", "")
    store.upsert_github_connection(user_id, str(user.get("id")), user.get("login", ""), encrypt_token(token), scopes)
    return {"login": user.get("login"), "id": user.get("id")}


def get_token(user_id: str) -> str:
    row = store.get_github_connection(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="no github connection")
    return decrypt_token(row["encrypted_access_token"])


async def list_repos(user_id: str) -> list[dict[str, Any]]:
    token = get_token(user_id)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GITHUB_API}/user/repos?per_page=100&sort=updated", headers=_headers(token))
        r.raise_for_status()
        return r.json()


async def get_contents(user_id: str, owner: str, repo: str, path: str) -> list[dict[str, Any]] | dict[str, Any]:
    token = get_token(user_id)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=_headers(token))
        r.raise_for_status()
        return r.json()


async def upsert_file(user_id: str, owner: str, repo: str, path: str, content_b64: str, message: str, branch: str, sha: str | None) -> dict[str, Any]:
    token = get_token(user_id)
    body: dict[str, Any] = {"message": message, "content": content_b64, "branch": branch}
    if sha:
        body["sha"] = sha
    async with httpx.AsyncClient() as client:
        r = await client.put(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=_headers(token), json=body)
        r.raise_for_status()
        return r.json()


async def create_branch(user_id: str, owner: str, repo: str, branch: str, base: str) -> dict[str, Any]:
    token = get_token(user_id)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{base}", headers=_headers(token))
        r.raise_for_status()
        base_sha = r.json()["object"]["sha"]
        r2 = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
            headers=_headers(token),
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        r2.raise_for_status()
        return r2.json()


async def open_pr(user_id: str, owner: str, repo: str, title: str, head: str, base: str, body: str) -> dict[str, Any]:
    token = get_token(user_id)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(token),
            json={"title": title, "head": head, "base": base, "body": body},
        )
        r.raise_for_status()
        return r.json()


def connection_status(user_id: str) -> dict[str, Any]:
    row = store.get_github_connection(user_id)
    if not row:
        return {"connected": False, "github_username": None}
    return {"connected": True, "github_username": row["github_username"], "scopes": row.get("scopes", "")}
