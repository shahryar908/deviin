"""Client for the in-guest envd HTTP API.

Windows cannot open the Firecracker TAP/guest network directly, so every
call is proxied through `wsl curl` (same pattern the Go vm package uses).
"""

import json
import os
import shlex
import subprocess

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_GUEST = "http://172.16.1.2:8080"
_active = {"url": os.environ.get("DEVIN_ENVD_URL", _DEFAULT_GUEST)}
_DEFAULT_TIMEOUT = 30.0


class SandboxError(Exception):
    pass


class SandboxUnreachable(SandboxError):
    pass


def set_envd_url(url: str) -> None:
    _active["url"] = url


def envd_url() -> str:
    return _active["url"]


def _curl(args: list[str], timeout: float = _DEFAULT_TIMEOUT) -> str:
    try:
        p = subprocess.run(
            ["wsl", "curl", "-s", "--max-time", str(int(timeout))] + args,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
    except subprocess.TimeoutExpired as e:
        raise SandboxUnreachable(f"envd request timed out: {e}") from e
    if p.returncode != 0:
        raise SandboxUnreachable(f"envd unreachable at {_active['url']}: {p.stderr.strip()}")
    return p.stdout


def health() -> dict:
    out = _curl([f"{_active['url']}/health"])
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise SandboxUnreachable(f"bad /health response: {out!r}")


def execute(language: str, code: str, timeout_ms: int | None = None) -> dict:
    body: dict = {"language": language, "code": code}
    if timeout_ms:
        body["timeout_ms"] = timeout_ms
    timeout = (timeout_ms / 1000 if timeout_ms else _DEFAULT_TIMEOUT) + 5
    out = _curl(
        [
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(body),
            f"{_active['url']}/execute",
        ],
        timeout=timeout,
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise SandboxUnreachable(f"bad /execute response: {out!r}")


def read_file(path: str) -> str:
    res = execute("sh", f"cat {shlex.quote(path)}")
    if res.get("exit_code") != 0:
        raise SandboxError(res.get("stderr") or res.get("error") or "read_file failed")
    return res.get("stdout", "")


def write_file(path: str, content: str) -> None:
    import base64

    b64 = base64.b64encode(content.encode()).decode()
    res = execute("sh", f"mkdir -p $(dirname {shlex.quote(path)}) && echo {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}")
    if res.get("exit_code") != 0:
        raise SandboxError(res.get("stderr") or res.get("error") or "write_file failed")


def list_dir(path: str = ".") -> str:
    res = execute("sh", f"ls -la {shlex.quote(path)}")
    if res.get("exit_code") != 0:
        raise SandboxError(res.get("stderr") or res.get("error") or "list_dir failed")
    return res.get("stdout", "")
