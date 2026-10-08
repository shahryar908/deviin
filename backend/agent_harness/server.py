"""Minimal HTTP server exposing the harness loop for UI testing."""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import agent
import github_service
import sandbox
import settings
import store

CURRENT_USER = "local"

app = FastAPI(title="devin harness")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    prompt: str


@app.get("/health")
def health() -> dict:
    try:
        return {"harness": "ok", "envd": sandbox.health()}
    except Exception as e:
        return {"harness": "ok", "envd": str(e)}


@app.post("/run")
def run(req: RunRequest) -> dict:
    store.init_db()
    task = store.create_task(req.prompt)
    store.set_status(task["id"], "working")
    store.add_event(task["id"], "task_created", req.prompt)
    try:
        result = agent.run(req.prompt, task_id=task["id"])
        store.set_status(task["id"], "completed", result=result)
        store.add_event(task["id"], "task_completed", result[:500] if result else "")
        return {"task_id": task["id"], "result": result}
    except Exception as e:
        store.set_status(task["id"], "failed", error=str(e))
        store.add_event(task["id"], "task_failed", str(e))
        return {"task_id": task["id"], "error": str(e)}


@app.get("/tasks")
def tasks(limit: int = 50) -> dict:
    store.init_db()
    return {"tasks": store.list_tasks(limit)}


@app.get("/tasks/{task_id}/events")
def task_events(task_id: str) -> dict:
    store.init_db()
    return {"events": store.list_events(task_id)}


@app.get("/github/connect")
def github_connect() -> dict:
    store.init_db()
    try:
        return {"url": github_service.auth_url(CURRENT_USER)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/github/callback")
async def github_callback(code: str, state: str):
    store.init_db()
    try:
        await github_service.do_callback(code, state)
    except HTTPException:
        raise
    return RedirectResponse(f"{settings.FRONTEND_URL}/?github=connected")


@app.delete("/github/disconnect")
def github_disconnect() -> dict:
    store.init_db()
    deleted = store.delete_github_connection(CURRENT_USER)
    if not deleted:
        raise HTTPException(status_code=404, detail="no connection")
    return {"deleted": True}


@app.get("/github/status")
def github_status() -> dict:
    store.init_db()
    return github_service.connection_status(CURRENT_USER)


@app.get("/github/repos")
async def github_repos() -> dict:
    store.init_db()
    try:
        return {"repos": await github_service.list_repos(CURRENT_USER)}
    except Exception as e:
        raise HTTPException(status_code=getattr(e, "status_code", 500), detail=str(e))


class CommitRequest(BaseModel):
    path: str
    content: str
    message: str
    branch: str = "main"
    sha: str | None = None


@app.post("/github/repos/{owner}/{repo}/commit")
async def github_commit(owner: str, repo: str, body: CommitRequest) -> dict:
    import base64
    b64 = base64.b64encode(body.content.encode()).decode()
    return await github_service.upsert_file(CURRENT_USER, owner, repo, body.path, b64, body.message, body.branch, body.sha)


@app.post("/github/repos/{owner}/{repo}/branches")
async def github_branch(owner: str, repo: str, branch: str, base: str) -> dict:
    return await github_service.create_branch(CURRENT_USER, owner, repo, branch, base)


@app.post("/github/repos/{owner}/{repo}/pulls")
async def github_pulls(owner: str, repo: str, title: str, head: str, base: str, body: str) -> dict:
    return await github_service.open_pr(CURRENT_USER, owner, repo, title, head, base, body)


@app.get("/github/repos/{owner}/{repo}/contents")
async def github_contents(owner: str, repo: str, path: str = "") -> dict:
    return await github_service.get_contents(CURRENT_USER, owner, repo, path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DEVIN_HARNESS_PORT", "8787")))
