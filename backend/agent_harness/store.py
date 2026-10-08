"""Task/session/event persistence so the harness is durable across restarts."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import os

DB_PATH = os.environ.get("DEVIN_DB", os.path.join(os.path.dirname(__file__), "devinharness.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_tasks (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','working','completed','failed')),
  result TEXT,
  error TEXT,
  created_at REAL,
  updated_at REAL
);
CREATE TABLE IF NOT EXISTS agent_sessions (
  id TEXT PRIMARY KEY,
  task_id TEXT REFERENCES agent_tasks(id),
  sandbox_instance TEXT,
  repo_name TEXT,
  workspace_cwd TEXT,
  vcpu INTEGER,
  memory_mib INTEGER,
  state TEXT,
  job_json TEXT,
  created_at REAL,
  updated_at REAL
);
CREATE TABLE IF NOT EXISTS agent_task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT REFERENCES agent_tasks(id),
  type TEXT NOT NULL,
  message TEXT NOT NULL,
  meta TEXT,
  created_at REAL
);

CREATE TABLE IF NOT EXISTS github_connections (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE,
  github_user_id TEXT,
  github_username TEXT,
  encrypted_access_token TEXT NOT NULL,
  scopes TEXT,
  created_at REAL,
  updated_at REAL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _connect() as c:
        c.executescript(_SCHEMA)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_task(prompt: str) -> dict[str, Any]:
    init_db()
    task_id = str(uuid.uuid4())
    now = time.time()
    with db() as c:
        c.execute(
            "INSERT INTO agent_tasks(id,prompt,status,created_at,updated_at) VALUES (?,?,?,?,?)",
            (task_id, prompt, "queued", now, now),
        )
    return {"id": task_id, "prompt": prompt, "status": "queued"}


def set_status(task_id: str, status: str, result: str | None = None, error: str | None = None) -> None:
    with db() as c:
        c.execute(
            "UPDATE agent_tasks SET status=?, result=COALESCE(?,result), error=?, updated_at=? WHERE id=?",
            (status, result, error, time.time(), task_id),
        )


def add_event(task_id: str, type_: str, message: str, meta: dict[str, Any] | None = None) -> None:
    with db() as c:
        c.execute(
            "INSERT INTO agent_task_events(task_id,type,message,meta,created_at) VALUES (?,?,?,?,?)",
            (task_id, type_, message, json.dumps(meta) if meta else None, time.time()),
        )


def create_session(task_id: str, sandbox_instance: str, repo_name: str | None = None,
                   workspace_cwd: str = "/workspace", vcpu: int = 1, memory_mib: int = 256) -> str:
    session_id = str(uuid.uuid4())
    now = time.time()
    with db() as c:
        c.execute(
            "INSERT INTO agent_sessions(id,task_id,sandbox_instance,repo_name,workspace_cwd,vcpu,memory_mib,state,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (session_id, task_id, sandbox_instance, repo_name, workspace_cwd, vcpu, memory_mib, "active", now, now),
        )
    return session_id


def get_task(task_id: str) -> dict[str, Any] | None:
    with db() as c:
        row = c.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?", (limit,))]


def list_events(task_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_task_events WHERE task_id=? ORDER BY created_at LIMIT ?", (task_id, limit))]


def upsert_github_connection(user_id: str, github_user_id: str, github_username: str,
                             encrypted_access_token: str, scopes: str) -> None:
    conn_id = str(uuid.uuid4())
    now = time.time()
    with db() as c:
        c.execute(
            "INSERT INTO github_connections(id,user_id,github_user_id,github_username,encrypted_access_token,scopes,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET github_user_id=excluded.github_user_id, github_username=excluded.github_username,"
            " encrypted_access_token=excluded.encrypted_access_token, scopes=excluded.scopes, updated_at=excluded.updated_at",
            (conn_id, user_id, github_user_id, github_username, encrypted_access_token, scopes, now, now),
        )


def get_github_connection(user_id: str) -> dict[str, Any] | None:
    with db() as c:
        row = c.execute("SELECT * FROM github_connections WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def delete_github_connection(user_id: str) -> bool:
    with db() as c:
        cur = c.execute("DELETE FROM github_connections WHERE user_id=?", (user_id,))
        return cur.rowcount > 0
